'''
Gintaras Valatka september 2021
BitBangin' PCM5102 audio dac into dc life

pico pins: bck = 2, lrck = 4, data = 4

Set params like int: {"1":"-2147483648","2":"2147483647"} <-- min/max
Or in HEX: {"1":"0x80000000","2":"0x7fffffff"}
Or in Volta if float: {"1":"1.23456789", "2":"2.3456789"}

int32_t 32bit = 2^32 =
    = -2147483648 - 0 - +2147483647 raw
    = 0x80000000 - 0x0 - 0x7fffffff

2.1Vrms = 5.9396Vp-p /2 
    = -2.969848.... - 0 - +2.969848....Volta

'''
import sys, math
from machine import Pin, UART
from rp2 import PIO, StateMachine, asm_pio
import json
import time
import _thread

i = 0x0
channels = 2
resolution = 32

'''Set whatever default you want on power on'''
# https://en.wikipedia.org/wiki/Two%27s_complement
#d1 = 0x7fffffff # +2147483647
#d2 = 0x80000000 # -2147483648
d1 = 0x0 # 0V
d2 = 0x0

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
freq = 16000 # or 32000 dma/irq is needed for faster speeds

# BCK (BCLK = bit clock) lrck * fs #
bck = freq * resolution * channels

# CLK (MCLK = "master " clock) for 4 wire
clk = 0

#print("clk:", clk, "bck:", bck, "lrck:", lrck)
print("clk: ", clk)
print("bck: ", bck)
print("lrck:", freq, "<--freq")

# https://github.com/raspberrypi/pico-extras/blob/master/src/rp2_common/pico_audio_i2s/audio_i2s.pio
@asm_pio(out_shiftdir=0, autopull=True, pull_thresh=resolution, sideset_init=(rp2.PIO.OUT_LOW, rp2.PIO.OUT_LOW), out_init=rp2.PIO.OUT_LOW)
def i2s_32():
    # 30 = Figure 14. I2S Audio Data Format(skip the first "beat")
    # Data Format: L-channel = LOW, R-channel = HIGH
    set(x, 30)
    wrap_target()
    #                              /--- LRCLK
    #                              |/-- BCLK
    #                              ||   page15
    label("Left")
    out(pins, 1)           .side(0b00)[1]
    jmp(x_dec, "Left")     .side(0b01)[1]
    out(pins, 1)           .side(0b10)[1]
    set(x, 30)             .side(0b11)[1]
    
    label("Right")
    out(pins, 1)           .side(0b10)[1]
    jmp(x_dec, "Right")    .side(0b11)[1]
    out(pins, 1)           .side(0b00)[1]
    set(x, 30)             .side(0b01)[1]
    
    wrap()

@asm_pio(out_shiftdir=0, autopull=True, pull_thresh=resolution, sideset_init=(rp2.PIO.OUT_LOW, rp2.PIO.OUT_LOW), out_init=rp2.PIO.OUT_LOW)
def left_justified_32():
    # 31 = Figure 13. Left Justified Audio Data Format, L-channel = HIGH, R-channel = LOW
    # Audio data word = 16-bit, BCK = 32, 48, 64f S
    # Audio data word = 24-bit, BCK = 48, 64f S
    # Audio data word = 32-bit, BCK = 64f S
    set(x, 31)
    wrap_target()
    #                              /--- LRCLK
    #                              |/-- BCLK
    #                              ||   page15
    label("Left")
    out(pins, 1)           .side(0b10)[1]
    jmp(x_dec, "Left")     .side(0b11)[1]
    out(pins, 1)           .side(0b00)[1]
    set(x, 30)             .side(0b01)[1]
    #set(x, 30)             .side(0b01)[0]
    #set(osr, 0xaaaaaaaa)   .side(0b11)[0]
    
    label("Right")
    out(pins, 1)           .side(0b00)[1]
    jmp(x_dec, "Right")    .side(0b01)[1]
    out(pins, 1)           .side(0b10)[1]
    set(x, 30)             .side(0b11)[1]
    #set(0xaaaaaaaa, osr)   .side(0b11)[0]
    wrap()
    
def sine():
    pass

ramp_up = []
def ramp_down(_min, _max, _freq):
    pass

for i in range(-2147483648, 2147483647, 33554432): # 134217728 = 32 steps
    ramp_up.append(i)

# Format: i2s, FMT pin 16 LOW
sm0 = rp2.StateMachine(0, i2s_32, freq=bck * 4, sideset_base=Pin(2), out_base=Pin(4))
sm0.active(True)

# Format: left justified, FMT pin 16 HIGH
#sm1 = rp2.StateMachine(1, left_justified_32, freq=bck * 4, sideset_base=Pin(2), out_base=Pin(4))
#sm1.active(True)

Vrms = 2.1
Vpeak = Vrms * math.sqrt(2)

# Volt peak to peak
Vpp = Vpeak * 2

# Voltbit = volts per bit
Vbit = Vpp / (2 ** resolution)

#uart0 = UART(0, 115200)
#uart1 = UART(1, 115200)
# Comms core
def core_two():
    global d1, d2, Vbit
    print("Set params like: {\"1\":\"-2147483648\",\"2\":\"2147483647\"}")
    print("Or in HEX: {\"1\":\"0x80000000\",\"2\":\"0x7fffffff\"}")
    print("Or in Volta: {\"1\":\"0.123456789\"}")
    
    while True:
        time.sleep_ms(500)
        s = input("<--- ")
        if s:
            print("--->", s)
            
            j = json.loads(s)
            
            if j:
                # "detect" if its float
                # this allows to use float & int in the same var
                # and "auto" detect/parse accordingly
                # if its float = sets volts
                # if int(dec or hex) = sets raw val
                if "1" in j:
                    if j["1"].find('.') > -1: 
                        d1 = int(float(j["1"]) / Vbit)
                        print("d1:", d1, "v:", d1 * Vbit)
                    else:
                        d1 = int(j["1"])
                        print("d1 raw:", d1, "volt:", d1 * Vbit)
                        
                if "2" in j:
                    if j["2"].find('.') > -1:
                        d2 = int(float(j["2"]) / Vbit)
                        print("d2:", d2, "v:", d2 * Vbit)
                    else:
                        d2 = int(j["2"])
                        print("d2 raw:", d2, "volt:", d2 * Vbit)
                        
_thread.start_new_thread(core_two, ())

while True:
    
    sm0.put(d1) # Left
    sm0.put(d2) # Right
    
    #for i in ramp_up:
    #    sm0.put(i)
    #    sm0.put(i)
    
    #for i in range(buff):
    #    sm0.put(sin[i])
    #    sm0.put(cos[i])
    #i = i + 8192

    #sm1.put(d1) # Left
    #sm1.put(d2) # Right
