'''
2021 September Gintaras Valatka
BitBangin' PCM5102 audio dac into a tracy tracer

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



rampUp = 1 # bool
rampMin =  -2.0 # Volt
rampMax =  2.0 # Volt
rampSteps = 128

stairUp = 1
stairMin = -2.0
stairMax = 2.0
stairSteps = 10

''' TODO
It needs "settle down" delays for ramp and stairs
Ramp could could be sin or triagle
'''
ramp = []
stair = []

_rampMin = int(rampMin / Vbit)
_rampMax = int(rampMax / Vbit)

if _rampMin < 0:
    rampRange = (_rampMin * -1) + _rampMax # change sign so we can add
else:
    rampRange = _rampMin + _rampMax

print("rampRange", rampRange)

rampStep = int(rampRange / rampSteps)
print("rampStep", rampStep)

print("_rampMin", _rampMin)
print("_rampMax", _rampMax)
print("ramp steps #", rampRange / rampStep)

print("-----------------------------")

_stairMin = int(stairMin / Vbit)
_stairMax = int(stairMax / Vbit)

if _stairMin < 0:
    stairRange = (_stairMin * -1) + _stairMax # change sign so we can add
else:
    stairRange = _stairMin + _stairMax


stairStep = int(stairRange / stairSteps)

print("_stairMin",  _stairMin)
print("_stairMax",  _stairMax)
print("stairRange", stairRange)
print("stairStep",  stairStep)
print("stairSteps", stairRange / stairStep)

if rampUp:    
    #for i in range(_rampMin, _rampMax, rampStep): didnt work
    #    ramp.append(0)
    ramps = _rampMin
    while ramps <= _rampMax:
        ramp.append(ramps)
        ramps = ramps + rampStep
else:
    #for i in range(_rampMax, _rampMin, -rampStep):
    #    ramp.append(0)
    ramps = _rampMax
    while ramps >= _rampMin:
        ramp.append(ramps)
        ramps = ramps - rampStep

if stairUp:
    #for i in range(_stairMin, _stairMax, stairStep):
    #    stair.append(i)
    stairs = _stairMin
    while stairs <= _stairMax:
        stair.append(stairs)
        stairs = stairs + stairStep
else:
    #for i in range(_stairMax, _stairMin, -stairStep):
    #    stair.append(i)
    stairs = _stairMax
    while stairs >= _stairMin:
        stair.append(stairs)
        stairs = stairs - stairStep

#print("ramp", ramp)
#print("stair", stair)

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
    for i in stair:
        for ii in ramp:
            sm0.put(i)
            sm0.put(ii)
            #sm0.put(i)
            #sm0.put(ii)
            #sm0.put(i)
            #sm0.put(ii)
            #sm0.put(i)
            #sm0.put(ii)

#sm0.put(0x80000000) # L min
#sm0.put(0x7fffffff) # R max
