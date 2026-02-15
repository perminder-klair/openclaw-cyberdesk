# Hardware Wiring Guide

Complete guide to connecting the HMMD mmWave Sensor and NeoPixel LED stick to Raspberry Pi.

## Required Components

| Item | Status |
|------|--------|
| Raspberry Pi | Have |
| HMMD mmWave Sensor (24GHz) | Have |
| NeoPixel Stick 8x RGB LED | Have |
| Female-to-Female Jumper Wires (20 pack) | Order |
| Male Header Pins | Order |
| Lead-Free Solder | Order |
| Soldering Iron | Have |

### Shopping Links (Pi Hut)

- [Female-to-Female Wires - £2.50](https://thepihut.com/products/premium-female-female-jumper-wires-20-x-6-150mm)
- [Male Header Pins - ~£2](https://thepihut.com/products/break-away-0-1-36-pin-strip-male-header-black-10-pack)
- [Lead-Free Solder - ~£5](https://thepihut.com/products/antex-lead-free-solder)

## Raspberry Pi GPIO Pinout Reference

```
        3.3V  [1]  [2]  5V
       GPIO2  [3]  [4]  5V
       GPIO3  [5]  [6]  GND
       GPIO4  [7]  [8]  GPIO14 (TXD)
         GND  [9]  [10] GPIO15 (RXD)
      GPIO17  [11] [12] GPIO18 (reserved for audio)
      GPIO27  [13] [14] GND
      GPIO22  [15] [16] GPIO23
        3.3V  [17] [18] GPIO24
 GPIO10/MOSI  [19] [20] GND
```

---

## Part 1: HMMD mmWave Sensor

### Sensor Pinout

```
┌─────────────────────────────┐
│  HMMD mmWave Sensor         │
│   J2 Connector:             │
│   ┌───┬───┬───┬───┬───┐    │
│   │3V3│GND│TX │RX │OT2│    │
│   └───┴───┴───┴───┴───┘    │
│    1   2   3   4   5        │
└─────────────────────────────┘
```

### Wiring Connections

| Sensor Pin | Wire Color | Pi Pin | Pi GPIO |
|------------|------------|--------|---------|
| 3V3 | Red | Pin 1 | 3.3V Power |
| GND | Black | Pin 6 | Ground |
| TX | Yellow | Pin 10 | GPIO15 (RXD) |
| RX | Green | Pin 8 | GPIO14 (TXD) |
| OT2 | - | Not connected | - |

**Important**: TX and RX cross over - sensor TX goes to Pi RX, sensor RX goes to Pi TX.

### Configuration

```bash
sudo raspi-config
# Navigate to: Interface Options → Serial Port
# Login shell over serial: No
# Serial port hardware enabled: Yes
# Reboot
```

### Test Connection

```bash
sudo apt install minicom
minicom -b 115200 -D /dev/serial0
# You should see data when motion is detected
# Press Ctrl+A then X to exit
```

---

## Part 2: NeoPixel Stick (8x RGB LED)

### Preparation: Solder Header Pins

The NeoPixel stick has solder pads, not pin headers. You need to solder header pins first.

#### Step 1: Break Off 4 Pins

```
Full strip: ▌▌▌▌▌▌▌▌▌▌▌▌▌▌▌▌▌▌▌▌▌▌
                 ↓
Snap off:   ▌▌▌▌  (4 pins only)
```

#### Step 2: Identify the Input Side (RIGHT)

```
    OUTPUT SIDE                    INPUT SIDE
    (for chaining)                 (connect here!)
    ┌─────────────────────────────────────────┐
    │ GND ○                               ○ GND │
    │DOUT ○   ○ ○ ○ ○ ○ ○ ○ ○            ○ DIN │
    │5VDC ○      "8 NeoPixel Stick"       ○ 5VDC│
    │ GND ○                               ○ GND │
    └─────────────────────────────────────────┘
```

#### Step 3: Solder Headers to Input Side

```
Insert pins from BACK, solder on back:

    FRONT (LEDs visible)
    ┌──────────────────┐
    │ ○ ○ ○ ○ ○ ○ ○ ○  │
    │          GND ○─┬─│
    │          DIN ○─┼─│── Pins through holes
    │         5VDC ○─┼─│
    │          GND ○─┴─│
    └──────────────────┘
           ↑
    Solder on BACK side
```

#### Soldering Tips

1. Heat pad + pin together (3-4 seconds)
2. Touch solder to joint, not iron
3. Lead-free solder needs ~350-380°C
4. Good joint = small shiny cone

### Wiring Connections

| NeoPixel Pin | Wire Color | Pi Pin | Pi GPIO |
|--------------|------------|--------|---------|
| 5VDC | Red | Pin 2 | 5V Power |
| GND | Black | Pin 6 | Ground |
| DIN | Blue | **Pin 19** | **GPIO10 (SPI MOSI)** |

> **Note**: GPIO10 is used instead of GPIO18 to keep GPIO18 free for I2S audio output.

---

## Complete Wiring Diagram

```
                 RASPBERRY PI GPIO HEADER
                 (pin 1 = top left)

    3.3V →  [1] ●── Red: Sensor 3V3    ● [2] ←── Red: NeoPixel 5VDC
            [3] ●                       ● [4]
            [5] ●                       ● [6] ←── Black: SHARED GROUND
            [7] ●                       ● [8] ←── Green: Sensor RX
            [9] ●                       ● [10] ←─ Yellow: Sensor TX
            [11] ●                      ● [12]
            [13] ●                      ● [14]
            [15] ●                      ● [16]
            [17] ●                      ● [18]  (reserved for audio)
 NeoPixel → [19] ●── Blue: DIN         ● [20]
```

### Ground Sharing

Both devices use Ground. Options:
1. Connect both black wires to Pin 6
2. Use Pin 6 for one, Pin 9 for other
3. Use a breadboard to split ground

---

## Assembly Checklist

### Before Starting
- [ ] Raspberry Pi powered OFF
- [ ] All components ready
- [ ] Header pins soldered to NeoPixel

### Sensor Connections
- [ ] Red: Sensor 3V3 → Pi Pin 1 (3.3V)
- [ ] Black: Sensor GND → Pi Pin 6 (Ground)
- [ ] Yellow: Sensor TX → Pi Pin 10 (RXD)
- [ ] Green: Sensor RX → Pi Pin 8 (TXD)

### NeoPixel Connections
- [ ] Red: NeoPixel 5VDC → Pi Pin 2 (5V)
- [ ] Black: NeoPixel GND → Pi Pin 6 or 9 (Ground)
- [ ] Blue: NeoPixel DIN → Pi Pin 19 (GPIO10)

### After Connecting
- [ ] Double-check all connections
- [ ] No loose wires
- [ ] No crossed wires
- [ ] Power on Raspberry Pi
- [ ] Configure serial port (raspi-config)
- [ ] Test sensor with minicom
- [ ] Test NeoPixels with Python script

---

## Troubleshooting

### Sensor Not Working
- Check TX/RX are crossed (sensor TX → Pi RX)
- Verify serial port enabled in raspi-config
- Check 3.3V power (NOT 5V)

### NeoPixels Not Lighting
- Check 5V power connection
- Verify GPIO10 (Pin 19) is used for data
- Enable SPI: `sudo raspi-config` → Interface Options → SPI → Enable
- Try level shifter if flickering
- Check solder joints

### Both Not Working
- Check ground connections
- Verify Pi is powered on properly
- Check for loose connections

---

---

## Part 3: WM8960 Hi-Fi Sound Card HAT

The sound HAT provides microphones and speaker output for voice AI.

### What's Included

- WM8960 Audio HAT
- 8Ω 5W Speaker
- Mounting screws

### HAT Features

```
┌─────────────────────────────────────────────────────────┐
│             WM8960 Hi-Fi Sound Card HAT                 │
│                                                         │
│   (MIC L)                              (MIC R)          │
│      ◉                                    ◉             │
│                                                         │
│   [3.5mm]    ┌────────┐     [Speaker]   [Button]        │
│    Jack      │ WM8960 │      + | -       GPIO17         │
│              └────────┘                                 │
│                                                         │
│            [40-pin Pass-through Header]                 │
└─────────────────────────────────────────────────────────┘
```

### Pins Used by HAT

| Function | GPIO Pins |
|----------|-----------|
| I2S Audio | GPIO18, 19, 20, 21 |
| I2C Control | GPIO2, GPIO3 |
| Button | GPIO17 |

**No conflicts** with sensor (GPIO14/15) or NeoPixel (GPIO10).

### Assembly Order

1. **First**: Connect sensor & NeoPixel wires to Pi GPIO
2. **Then**: Place WM8960 HAT on top (press firmly onto all 40 pins)
3. **Finally**: Connect speaker to HAT's screw terminals

### Speaker Connection

```
Included 8Ω 5W Speaker:
  Red wire (+)   → + terminal on HAT
  Black wire (-) → - terminal on HAT
```

### Software Setup

```bash
# Install driver
git clone https://github.com/waveshare/WM8960-Audio-HAT
cd WM8960-Audio-HAT
sudo ./install.sh
sudo reboot

# Test speaker
speaker-test -t wav -c 2

# Test microphone (record 5 seconds)
arecord -D plughw:1,0 -f cd -d 5 test.wav
aplay test.wav
```

### Troubleshooting

#### No Sound
- Check speaker wire polarity (+ to +, - to -)
- Run `aplay -l` to verify card is detected
- Check volume: `alsamixer`

#### Microphone Not Working
- Run `arecord -l` to verify capture device
- Check mic isn't muted in `alsamixer`

---

## Complete Assembly Diagram

```
         ┌─────────────────────────┐
         │   WM8960 Sound HAT      │  ← Speaker connects here
         │   (on TOP)              │
         └───────────┬─────────────┘
                     │ (passes through 40 pins)
         ┌───────────┴─────────────┐
         │    RASPBERRY PI         │
         │                         │
         └───────────┬─────────────┘
                     │
    ┌────────────────┼────────────────┐
    │                │                │
    ↓                ↓                ↓
 Pin 1            Pin 6-10         Pin 19
 (3.3V)           (GND, TXD,       (GPIO10)
    │              RXD)               │
    │                │                │
    ↓                ↓                ↓
┌────────┐      ┌─────────┐     ┌──────────┐
│ Sensor │      │ Sensor  │     │ NeoPixel │
│  3V3   │      │GND/TX/RX│     │   DIN    │
└────────┘      └─────────┘     └──────────┘
```

---

## Safety Reminders

- Always power OFF Pi before connecting/disconnecting wires
- Sensor uses 3.3V - never connect to 5V
- Double-check connections before powering on
- Connect ground first, disconnect ground last
