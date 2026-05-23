# Hardware Build Guide

Complete guide for building a rotary phone VoIP controller with Raspberry Pi.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     ROTARY PHONE                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐ │
│  │  Rotary  │  │   Hook   │  │ Handset  │  │   Ringer    │ │
│  │   Dial   │  │  Switch  │  │ Speaker  │  │   (bell)    │ │
│  │          │  │          │  │   +Mic   │  │             │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬──────┘ │
│       │             │             │               │         │
└───────┼─────────────┼─────────────┼───────────────┼─────────┘
        │             │             │               │
        │ GPIO        │ GPIO        │ USB Audio     │ GPIO+Amp
        │             │             │               │
┌───────┴─────────────┴─────────────┴───────────────┴─────────┐
│                    RASPBERRY PI ZERO 2 W                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Python Control Software                 │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌───────────┐  │   │
│  │  │  Dial   │ │  Hook   │ │  Audio  │ │    SIP    │  │   │
│  │  │ Reader  │ │ Monitor │ │ Router  │ │  Client   │  │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────┬─────┘  │   │
│  └────────────────────────────────────────────┼────────┘   │
│                                               │             │
│                                          WiFi │             │
└───────────────────────────────────────────────┼─────────────┘
                                                │
                                                ▼
                                    ┌───────────────────┐
                                    │     VoIP.ms       │
                                    │   SIP Server      │
                                    │                   │
                                    │  ──────────────── │
                                    │        │          │
                                    │        ▼          │
                                    │      PSTN         │
                                    │  (Real phones)    │
                                    └───────────────────┘
```

## Bill of Materials

### Core Electronics (~$40-50)

| Component | Model | Est. Cost | Notes |
|-----------|-------|-----------|-------|
| Single-board computer | Raspberry Pi Zero 2 W | $15 | WiFi built-in, fits in most phone cases |
| MicroSD card | 16GB+ Class 10 | $8 | For Raspberry Pi OS |
| USB audio adapter | Sabrent AU-MMSA or similar | $8 | Must be USB-A; get a micro-USB OTG adapter |
| Handset receiver speaker | 8Ω 0.5–1W, 28–36mm round | $2 | Replacement element; matches USB headphone output directly |
| Handset microphone | Electret condenser capsule, 6–10mm | $2 | Replacement element; works on USB plug-in power |
| Ringer speaker | 3W 4Ω speaker + PAM8403 amp | $5 | Small class-D amp module |
| USB-C breakout | Panel-mount USB-C to bare wires | $3 | For 5V wall-wart power input |
| USB-C wall adapter | 5V 2A+ (10W+) USB-C PSU | $8 | Any standard phone charger works |

### Connectors & Wiring (~$10-15)

| Component | Qty | Notes |
|-----------|-----|-------|
| Dupont jumper wires | 20 | Female-to-female for GPIO |
| 22 AWG hookup wire | 10 ft | For internal wiring |
| 10kΩ resistors | 4 | Pull-ups for GPIO inputs |
| 3.5mm audio jack (optional) | 1 | If handset uses standard plug |
| Heat shrink tubing | Assorted | For clean connections |

### Tools Needed

- Soldering iron + solder
- Wire strippers
- Multimeter
- Small screwdrivers (phone disassembly)
- Hot glue gun (mounting components)

### Total Estimated Cost: **$50-65 per phone**

---

## Wiring Guide

### Understanding Your Rotary Phone

Most rotary phones have these internal connections:

1. **Hook switch**: Opens/closes when handset is lifted/replaced
2. **Rotary dial**: Pulses a switch N times for digit N (0 = 10 pulses)
3. **Handset**: Contains speaker + carbon/dynamic microphone
4. **Ringer**: Electromagnetic bell (we'll bypass this—needs 90V AC)

**Before wiring**: Open your phone, take photos, and trace the existing wires. Use a multimeter in continuity mode to identify:
- Which wires go to the hook switch
- Which wires pulse when you dial
- Which wires go to the handset speaker/mic

### GPIO Pin Assignments

| Function | GPIO (BCM) | Physical Pin | Notes |
|----------|------------|--------------|-------|
| Hook switch | GPIO 17 | Pin 11 | HIGH = on-hook, LOW = off-hook |
| Dial pulse | GPIO 27 | Pin 13 | Pulses LOW for each digit |
| Dial active | GPIO 22 | Pin 15 | LOW while dial is rotating (optional but helpful) |
| Ringer amp enable | GPIO 23 | Pin 16 | HIGH to enable ringer speaker |
| Ground | GND | Pin 6, 9, 14, etc. | Common ground |

### Wiring Diagram

```
                                    RASPBERRY PI ZERO 2 W
                                    ┌────────────────────┐
                                    │ (USB/Power on left)│
                                    │                    │
HOOK SWITCH ─────┬──── 10kΩ ───────│─ 3.3V (Pin 1)     │
                 │                  │                    │
                 └─────────────────│─ GPIO17 (Pin 11)   │
                 │                  │                    │
                 └── (other leg) ──│─ GND (Pin 9)       │
                                    │                    │
DIAL PULSE ──────┬──── 10kΩ ───────│─ 3.3V (Pin 1)     │
                 │                  │                    │
                 └─────────────────│─ GPIO27 (Pin 13)   │
                 │                  │                    │
                 └── (other leg) ──│─ GND               │
                                    │                    │
DIAL ACTIVE ─────┬──── 10kΩ ───────│─ 3.3V             │
(optional)       │                  │                    │
                 └─────────────────│─ GPIO22 (Pin 15)   │
                 │                  │                    │
                 └── (other leg) ──│─ GND               │
                                    │                    │
                              ┌────│─ GPIO23 (Pin 16)   │
                              │     │                    │
                              │     │      ┌── USB ─────│─ USB (for audio adapter)
                              │     │      │            │
                              │     └──────┴────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   PAM8403 Amp   │
                    │                 │
                    │  VCC ◄──────────┼─── 5V from Pi (Pin 2 or 4)
                    │  GND ◄──────────┼─── GND
                    │  EN  ◄──────────┘ (GPIO23 amp enable)
                    │                 │
                    │  L+/L- ─────────┼───► Speaker (3W 4Ω)
                    │                 │
                    │  R IN ◄─────────┼─── USB audio out (parallel with handset)
                    └─────────────────┘


HANDSET ────────────────────────────────────────────────────────

  Speaker (+) ──────────► USB Audio "Headphone" left channel
  Speaker (-) ──────────► USB Audio "Headphone" ground

  Mic (+) ──────────────► USB Audio "Mic" signal
  Mic (-) ──────────────► USB Audio "Mic" ground


POWER SYSTEM ───────────────────────────────────────────────────

  USB-C wall wart (5V 2A+) ──► USB-C cable ──► USB-C breakout

  USB-C breakout VBUS ──► Pi Zero "5V"  (Pin 2 or 4)
  USB-C breakout GND  ──► Pi Zero "GND" (Pin 6)
```

> **Note**: Feeding 5V directly into the Pi's GPIO 5V pin bypasses the
> board's input polyfuse. That's fine for a fixed indoor install with
> a known-good supply, but use a reputable wall wart and don't hot-swap
> the USB-C cable under load.

### Hook Switch Wiring Detail

The hook switch is typically a simple SPST switch. When the handset is **on the hook** (hung up), the switch is **open**. When **off hook** (lifted), it's **closed**.

```
        ┌─────────────┐
        │ Hook Switch │
  ──────┤             ├──────
   (A)  │   ┌───┐     │  (B)
        │   │   │     │
        │   └───┘     │
        │  (plunger)  │
        └─────────────┘

  Wire A ──► GPIO17
  Wire B ──► GND

  Plus: 10kΩ pull-up from GPIO17 to 3.3V

  Result: GPIO17 reads HIGH when on-hook, LOW when off-hook
```

### Rotary Dial Wiring Detail

The rotary dial has two switches:
1. **Pulse switch**: Opens/closes rapidly as dial returns (10 pulses/sec)
2. **Off-normal switch**: Closes while dial is pulled away from rest position

```
  When you dial "5":

  Off-normal: ___________/‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾\___________
                         ↑ dial pulled                  ↑ dial returns to rest

  Pulse:      ___________/‾\_/‾\_/‾\_/‾\_/‾\___________________________
                           1   2   3   4   5  (5 pulses = digit 5)

  Time:       |──────────|─────────────────────|──────────────────────|
              0ms      ~100ms               ~600ms                  ~800ms
```

Wire the pulse switch to GPIO27 with a 10kΩ pull-up. The software will:
1. Detect dial activity (GPIO27 going LOW)
2. Count pulses
3. After ~300ms of no pulses, register the digit


### USB Audio Wiring Detail

The two-jack USB sound card has a microphone input and a headphone/line output, both 3.5mm TRS. This section covers identifying each jack, the connector pinout, and how the handset and ringer share the single output.

#### Identifying which jack is which

Three methods, in order of reliability:

1. **Icons or color** — most dongles mold a tiny mic/headphone icon next to each jack, or use the standard color code: **green = output, pink = mic input**.

2. **Software check** (most reliable):
   ```bash
   arecord -l    # capture (mic) devices
   aplay -l      # playback devices

   # Test output — should hear tone in whatever's plugged into this jack
   speaker-test -D plughw:CARD=Device -c 2 -t sine

   # Test input — record 3s then play back
   arecord -D plughw:CARD=Device -f cd -d 3 /tmp/test.wav && aplay /tmp/test.wav
   ```

3. **Multimeter** — with the dongle powered (plugged into USB), the mic jack tip usually reads 2.5–5V of plug-in power. The output jack tip reads 0V.

#### 3.5mm TRS pinout

```
         ┌── TIP    = Left channel (output) / Mic signal (input)
         ├── RING   = Right channel (output) / Bias or unused (input)
         └── SLEEVE = Ground (both)
```

Easiest source for wiring: a "3.5mm to bare wire pigtail" (5-pack ~$7 on Amazon). Or strip the end off a 3.5mm cable — typically red = tip/L, white = ring/R, bare = sleeve/GND.

#### Handset wiring

The simplest, most reliable path is to **replace the handset's original mic and speaker** with modern equivalents that match the USB sound card directly. This avoids carbon-mic bias circuits and the ~150Ω receiver impedance mismatch entirely, and modern parts won't have the age-related degradation common in 50–70 year old elements. Total parts cost ~$4. See [Keeping the original elements](#keeping-the-original-elements) below if you'd rather preserve the originals.

##### Replacement parts

| Element | Spec | Notes |
|---|---|---|
| Receiver speaker | 8Ω 0.5–1W, 28–36mm round | Search "8 ohm 36mm speaker". 36mm fits snugly in WE500-style caps; 28mm leaves room for foam. |
| Microphone | Electret condenser capsule, 6–10mm | Search "electret microphone capsule 9.7mm". CUI CMC-9745 is a common choice. |

Both elements pop into the original handset caps. Reuse the existing handset wires going back into the phone body — unsolder the old elements and solder on the new ones.

##### Wiring

```
Receiver speaker (+) ──► tip  (or tip+ring tied for L+R sum)
Receiver speaker (–) ──► sleeve (GND)

Electret mic (+)     ──► tip       (polarity matters; the lead with continuity
Electret mic (–)     ──► sleeve     to the capsule's metal can is GND)
                         (ring left unconnected)
```

For the speaker, single-tip or tip+ring tied together both work — mono WAVs through ALSA duplicate to both channels anyway.

##### Mounting

- **Speaker**: foam-pad it into the receiver cap with the diaphragm facing the earpiece holes; hot glue around the rim. Don't get glue on the cone.
- **Microphone**: mount it pointing toward the mouthpiece holes with foam around it to reduce handling noise. The original screw terminals or springs in the cap can clip onto its leads.
- Keep the original elements in a baggie taped inside the phone base if you ever want to swap back.

#### Sharing the output between handset and ringer

The handset receiver and the PAM8403 amp input both tap the same headphone output, in parallel. They're never *audibly* active at the same time because GPIO23 gates the amp's EN pin:

```
                                ┌──► Handset receiver (~150Ω)
USB output ─── tip ─────────────┤
(headphone)                     │
                                └──► PAM8403 R IN (high-Z)
                                          │ EN ◄── GPIO23
                                          ▼
                                       Ringer speaker
```

- **On hook, ringing**: GPIO23 HIGH → ringer plays. Signal also reaches the handset receiver, but it's in the cradle — silent.
- **Off hook, in call**: GPIO23 LOW → amp muted, ringer silent. Handset plays normally.
- **Off hook, dial tone / DTMF**: GPIO23 LOW → played only through the handset receiver.

Signal ground goes to the sleeve of the audio cable. The PAM8403's *power* GND goes to the Pi ground rail. They meet inside the USB cable — don't run a separate ground wire between them.

If you find audible bleed through the ringer speaker when the amp is supposed to be muted, swap to an analog switch (74HC4053, ADG719) for hard routing instead of relying on the EN pin.

#### Keeping the original elements

If the phone is a collector's piece and you want to preserve the originals, identify the pairs with a multimeter:

- **Speaker pair**: telephone receivers are typically ~150Ω, stable resistance
- **Mic pair**: behavior depends on mic type — see below

Wiring is the same shape as the replacement path (receiver → output jack, mic → mic input jack), but plan for two complications:

**1. Receiver impedance mismatch.** 150Ω telephone receivers vs. the ~32Ω that USB headphone outputs are designed to drive. Audio will be quieter and may sound tinny. Compensate with software gain in `audio_handler.py` (modest amounts only — too much adds clipping/distortion), or add a small 1:5 audio transformer for proper impedance matching.

**2. Carbon mic bias** (pre-1980s US phones — Western Electric 500/554, ITT, etc.). Carbon microphones need several volts of DC bias to produce signal. USB sound cards provide plug-in power intended for electret capsules, which usually isn't enough to drive a carbon mic cleanly.

- **Test for carbon**: with a multimeter across the mic pair, tap the mouthpiece sharply. Resistance jumping around in the ~50–200Ω range = carbon. Stable higher resistance = dynamic or electret.
- **Bias circuit**: feed ~5V through a ~200Ω series resistor into the mic, then capacitively couple the AC signal through a 1:1 audio transformer into the USB sound card's mic input. Schematics for "carbon mic to electret input adapter" are widely documented.

Newer phones (1980s+) typically have dynamic or electret mics that work straight from the USB sound card with no extra circuitry — only the impedance mismatch on the receiver applies.


## Assembly Tips

### Phone Disassembly Notes

**Common US phones** (Western Electric 500/554, ITT):
- Remove 4 screws on bottom
- Housing lifts off, exposing internals
- Bell gongs are held by a single screw
- Network block (where wires terminate) usually has screw terminals

**UK phones** (GPO 746):
- Slightly different dial mechanism (may need pulse timing adjustment)
- Same general approach

### Fitting Components

1. **Remove the bell gongs** (we're replacing with a speaker)
   - Keep them if you want to attempt high-voltage ringer later

2. **Pi Zero 2 W placement**: Fits easily where the bell coil was
   - Use standoffs or hot glue on non-conductive surface
   - Ensure GPIO pins are accessible

3. **USB-C breakout placement**: Panel-mount through the case where the original phone cord exited, so the wall wart cable enters cleanly. Short pigtail to the Pi's 5V/GND pins.

4. **Speaker**: Mount where bell was, facing downward through vents
   - 3W is plenty loud for ringing

### Handset Wiring

See [USB Audio Wiring Detail](#usb-audio-wiring-detail) above for jack identification, pinout, parallel ringer wiring, and microphone notes.
