'''
2021 September Gintaras Valatka
BitBangin' PCM5102 audio dac into sin and cos

pico pins: bck = 2, lrck = 4, data = 4

Set params like int: {"1":"-2147483648","2":"2147483647"} <-- min/max
Or in HEX: {"1":"0x80000000","2":"0x7fffffff"}
Or in Volta if float: {"1":"1.23456789", "2":"2.3456789"}

int32_t 32bit = 2^32 =
= -2147483648 - 0 - +2147483647
= 0x80000000 - 0x0 - 0x7fffffff

2.1Vrms = 5.9396Vp-p /2 = ~ -2.969848.... - 0 - +2.969848....V
'''

import math
from machine import Pin
from rp2 import PIO, StateMachine, asm_pio

# this appears to be slower than var=[]
# see _buffL/_buffR
# to test, replace buffL[i]/buffR[i] with _buffL[i]/_buffR[i] in sm0.put()
from array import array

# For 3 wire, as in NO CLK
# See Table 11. BCK Rates (MHz) by LRCK Sample Rate for PCM510xA PLL Operation
''' in kHz
samp. bck     bck
rate  32fs    64fs
8     –       –
16    –       1.024
32    1.024   2.048
44.1  1.4112  2.8224
48    1.536   3.072
96    3.072   6.144
192   6.144   12.288
384   12.288  24.576
'''
# for 2ch x 32bit we need 64 min
fs = 64 

# also LRCK (LRCLK = left right clock, WS = word select, FS = frame sync)
freq = 16000 # dma/irq is needed for faster speeds @ 32Bit x 2ch

channels = 2
resolution = 32 # future 24/16/8
resolutionT = 2 ** resolution # total values

# BCK (BCLK = bit clock) lrck * fs #
bck = freq * resolution * channels
print("bck:", bck)

Vrms = 2.1
Vp = Vrms * math.sqrt(2)
Vpp = Vp * 2
Vbit = Vpp / resolutionT # Voltbit = Volts per bit

# if buffer is 360, then 'phase' acts like phase, so 90 would produce 90° degree etc
# if buffer is eg: 32, setting 'phase'=offsetting the buffer to 32/2=16 would be 180° phase offset
# 32/4 = 8 = 90°, (32/4)*3 = 240 = 270°
# 16 = 1000Hz = freq/buff
steps = 16 # larger buffer = slower sin :D
print("freq:", freq / steps)

# sin
phaseL = 0 # this is buffer offset not exactly 'phase'
attenL = 1.0     # 0.0 - 1.0
dcOffsetL = 0.0 # Volts

phaseR = 0 # steps / 4 #  = 90°
attenR = 1.0
dcOffsetR = 0.0
typeRcos = True # False to sin

#_buffL = array('L', int(0x7fffffff * (0.9 * math.sin(2 * math.pi * i / steps))) for i in range(phaseL, steps))
#_buffR = array('L', int(0x7fffffff * (0.9 * math.cos(2 * math.pi * i / steps))) for i in range(phaseR, steps))
#_joint = array('L', int(0x7fffffff * (0.9 * math.sin(2 * math.pi * i / steps*2))) for i in range(phaseL, steps*2))

buffL = []
buffR = []
tau = 2 * math.pi # xN to place n number of waves into the buffer, also speeds up freq, or leave just pi for half wave

dcL = int(dcOffsetL / Vbit)
dcR = int(dcOffsetR / Vbit)

# https://learn.bela.io/tutorials/c-plus-plus-for-real-time-audio-programming/wavetables/
# https://docs.micropython.org/en/latest/library/pyb.DAC.html
for i in range(steps):

    ''' L '''
    # so this makes numbers from -1.0 to 1.0
    LL = math.sin(tau * (i + phaseL) / steps)
    if LL > 0:
        LL = int(LL * 0x7fffffff * attenL) + dcL # multiply by max and conver to int, add offset
        if LL > 0x7fffffff: # limit to max if dc offset is over positive range
            LL = 0x7fffffff
    if LL < 0:
        LL = int(LL * 0x80000000 * attenL) + dcL # multiply by min
        #if LL ? 0x80000000: # limit to mim if dc offset is over negative range
        #    LL = 0x80000000
    if LL == 0:
        LL = 0

    ''' R '''
    if typeRcos:
        RR = math.cos(tau * (i + phaseR) / steps)
    else:
        RR = math.sin(tau * (i + phaseR) / steps)
        
    if RR > 0:
        RR = int(RR * 0x7fffffff * attenR) + dcR
        if RR > 0x7fffffff:
            RR = 0x7fffffff
    if RR < 0:
        RR = int(RR * 0x80000000 * attenR) + dcR
        #if ?dc_offsetR :
        #    RR = 0x80000000
    if RR == 0:
        RR = 0

    buffL.append(LL)
    buffR.append(RR)
    
    ''' casting works, raw does not '''
    #buffL.append(_buffL[i])
    #buffR.append(_buffR[i])

print("buffL", buffL)
#print("buffR", buffR)

@asm_pio(
    out_shiftdir=PIO.SHIFT_LEFT,
    autopull=True,
    pull_thresh=resolution,
    #fifo_join=PIO.JOIN_RX,
    sideset_init=(PIO.OUT_LOW, PIO.OUT_LOW),
    out_init=PIO.OUT_LOW
)
def _i2s_32():
    #n = 0
    resolution = 32
    r = resolution - 2

    set(x, r)
    wrap_target() #                /--- LRCLK
                  #                |/-- BCLK
    label("Left") #                ||   page15
    out(pins, 1)           .side(0b00)[1]
    jmp(x_dec, "Left")     .side(0b01)[1]
    out(pins, 1)           .side(0b10)[1]
    set(x, r)              .side(0b11)[1]
    
    label("Right")
    out(pins, 1)           .side(0b10)[1]
    jmp(x_dec, "Right")    .side(0b11)[1]
    out(pins, 1)           .side(0b00)[1]
    set(x, r)              .side(0b01)[1]
    
    wrap()

sm0 = rp2.StateMachine(0, _i2s_32, freq=bck * 4, sideset_base=Pin(2), out_base=Pin(4))
sm0.active(True)

while True:
    #sm0.put(0x80000000) # L min
    #sm0.put(0x7fffffff) # R max
    for i in range(steps):
        sm0.put(buffL[i])
        sm0.put(buffR[i])
        #sm0.put(_buffL[i])
        #sm0.put(_buffR[i])
    #for i in _buffL:
    #    sm0.put(i)
    #    sm0.put(i)

'''
res = {
    "8": {
        "min":0x80,
        "max":0x7f,
        "total":2**8
        },
    "16": {
        "min":0x8000,
        "max":0x7fff,
        "total":2**16
        },
    "24": {
        "min":0x80000000,
        "max":0x7fffff00,
        "total":2**24
        },
    "32": {
        "min":0x80000000,
        "max":0x7fffffff,
        "total":2**32
        },
    }
'''
