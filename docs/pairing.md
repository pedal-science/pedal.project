# Pairing, and the pedal's own network

**Status:** design, 2026-10-01 (the plan's Phase 5). It settles how a phone finds the pedal, what the
pedal's network is, where the passphrase lives, what the app stores, what proves a phone is the
owner's, and what fails. Decisions that are yours are marked **yours**; the proposal beside each says
why. It pays off the debt register's "the app needs the home network".

The pieces it leans on: [uart-protocol.md](uart-protocol.md) (draft 3 adds two messages),
[pedal-service.md](pedal-service.md) (the service hands the Pico what the app needs), `devices/` (the
Core host's access point) and `firmware/` (the Pico's BLE). The app work is ljoss's; ljoss's
`AGENTS.md` points back here for the system context, and this file stays the one home for the design.

## The goal, as someone meets it

- **The first meeting.** Power the pedal on, open ljoss, tap **Add Pedal**, put the pedal in setup
  mode. A system sheet shows the pedal's picture and name; tap it. The phone joins the pedal's Wi-Fi
  and the app is connected. No address typed, no token pasted, no network chosen.
- **Later.** Power the pedal on, open ljoss: it joins the pedal's network and connects. No sheet, no
  prompt, no code.
- **Someone else's phone.** Does not see the pedal: it only advertises when it is in setup mode, which
  is a gesture and a short window.
- **Forgetting.** Remove the pedal in ljoss, or use the pedal's forget gesture. The bond goes, the
  passphrase rotates, and the pedal forgets the phone.
- **The Mac.** AccessorySetupKit is iOS and iPadOS only (Mac Catalyst 26+ at most), so ljoss on the
  Mac keeps the manual path — host, port, token — and can read the pedal's network from a QR on the
  display when Phase 3.7 exists.

## What Apple gives us, and what it does not

AccessorySetupKit (iOS 18+; the app uses it from iOS 27, which is ljoss's floor) is the system sheet
the request describes. Its rules, as documented:

- The app declares what it may find in `Info.plist`: `NSAccessorySetupKitSupports` (`Bluetooth` and/or
  `WiFi`), `NSAccessorySetupBluetoothServices` (upper-cased UUID strings), optionally
  `NSAccessorySetupBluetoothNames` and `NSAccessorySetupBluetoothCompanyIdentifiers`. A descriptor
  rule that the plist does not declare terminates the app when the picker is shown.
- The picker is the app's to describe and the system's to draw: `ASPickerDisplayItem` carries the
  name and `UIImage` the sheet shows (in a 180×120 pt box; supply about 540×360 px, transparent), and
  the system adds the advertised Bluetooth name and the app's name so the person can check
  authenticity. The same image appears in Settings.
- Discovery matches the **advertisement**, not the GATT database: the service UUID must be in the
  advertising data, or the accessory never appears. A name substring alone is not enough — it needs a
  service UUID or a company identifier beside it.
- The descriptor can also match Wi-Fi: `ssid` (exact) and `ssidPrefix`. A descriptor with both
  Bluetooth and Wi-Fi rules matches an accessory that satisfies all of them, and the system grants
  both interfaces with one tap. `ASAccessory` then carries `bluetoothIdentifier` and `ssid`.
- After the tap the app talks to the accessory as usual: `bluetoothIdentifier` →
  `CBCentralManager.retrievePeripherals(withIdentifiers:)` → connect → GATT. Scanning is not needed
  and only ASK-paired accessories come back; no `NSBluetoothAlwaysUsageDescription` and no Bluetooth
  permission prompt.
- `ASPickerDisplayItem.setupOptions`: `.rename`, `.finishInApp`, `.confirmAuthorization`. The last
  means the app must prove authorization by reading a **protected GATT characteristic** (the
  accessory "supports `bluetoothPairingLE`"); the picker then shows the numeric-comparison or
  passkey UI, and the system makes the bond. `.finishInApp` leaves the accessory partially
  authorized until the app calls `finishAuthorization(for:settings:)` — documented for an accessory
  with two interfaces whose full SSID arrives after onboarding.
- Wi-Fi joining is `NEHotspotConfigurationManager.joinAccessoryHotspot(_:passphrase:)` or
  `joinAccessoryHotspotWithoutSecurity(_:)` (iOS 18+). WPA/WPA2/WPA3 Personal, 8–63 character
  passphrase. **It implicitly sets `joinOnce = YES`, and there is no API for a persistent join.**
  Ordinary `NEHotspotConfiguration.apply` for the same SSID is refused with "system denied" while the
  accessory is ASK-added.
- `joinOnce` means the association lives only while the app is in the foreground: the system
  disconnects and forgets it after **15 seconds in the background**, on sleep, on quit, or when the
  phone joins another network. `removeConfiguration(forSSID:)` leaves early.
- The Hotspot Configuration capability (`com.apple.developer.networking.HotspotConfiguration`) is
  required for the join calls, and the provisioning profile has to be regenerated to include it.
- The Local Network permission is unchanged: reaching `namchaind` on the pedal's network still needs
  it, and ljoss already asks and reports it.

What ASK does **not** give us:

- **No passphrase handover.** The framework joins the accessory's network; it does not know or carry
  its passphrase. The accessory has to tell the app, over its own channel — here, BLE.
- **No persistent Wi-Fi.** Every session begins with a join the app performs, silently or not; the
  phone does not remember the pedal's network, which is also why it will not hijack the owner's home
  Wi-Fi. It does mean the app must re-join after 15 s in the background.
- **Nothing on the Mac**, and nothing scriptable: the picker cannot be driven from a test harness, so
  the Apple half is tested on a real phone.
- **No answer about an accessory already bonded elsewhere.** The picker's behaviour when the pedal is
  bonded to another phone is the accessory's problem to solve (setup mode, bonds, a forget gesture).

## The shape

```
   ljoss (iOS)                         the pedal
   ┌──────────┐    BLE (advertisement, bond, GATT)   ┌────────────┐
   │  ASK     │ ◄──────────────────────────────────► │   Pico     │  BLE only; the record,
   │  picker  │      the provisioning bundle         │            │  the bonds, setup mode
   └────┬─────┘                                      └─────┬──────┘
        │ NEHotspotConfiguration (joinAccessoryHotspot)    │ UART: PROV/PAIR
        │                                                  │
   ┌────▼─────┐      the pedal's own Wi-Fi network   ┌─────▼──────┐
   │  Wi-Fi   │ ◄──────────────────────────────────► │ Core host  │  hostapd AP, DHCP, mDNS,
   │          │      namchaind (47810), HTTP (47820) │  + pedald  │  the derived cache
   └──────────┘                                      └────────────┘
```

- **The Core host runs the access point.** The phone must reach `namchaind`, which is the Core host,
  and the Pico cannot route IP: with the Pico as the access point the Core host would be a station
  whose traffic every packet is relayed through the Pico's single radio, at half throughput and beside
  its BLE. `hostapd` on the Core host's `wlan0` is well-trodden (brcmfmac AP mode, a static address,
  a DHCP server), the configuration belongs in `devices/` with the rest, and `backup` already covers
  the state. The Pico keeps what suits it: the advertisement iOS pairs to, the bond, the record, and
  the display. **Proposed; the runner-up is the Pico as the access point** (one device for both
  interfaces, up in milliseconds), rejected unless the spike below says the Core host's AP is unusable.
- **The pedal is not on any other network.** In the pedal root, `wlan0` is the access point and the
  station path retires; `eth0` stays a DHCP client for the bench, where a cable gives the same
  `ssh vip` loop as today. The rescue root keeps its station configuration, so the way back in does
  not depend on the pedal's own AP. The image stops writing the house Wi-Fi secret into the pedal
  root; the pedal root has no secret but the pedal's own.
- **The network is the pedal's, and it is up whenever the pedal is.** SSID `Pedal-XXXX`, where `XXXX`
  is generated once and stored (from the Pico's unique id, so two pedals differ); `hostapd` in 2.4 GHz
  (`hw_mode=g`, a fixed channel, `country_code=GB`, WPA2-PSK/CCMP) with a passphrase of 24 characters
  from a 32-symbol alphabet, so nothing needs escaping in a config file; a fixed address for the Core
  host (`10.77.0.1/24`, proposed) and a DHCP pool above it; the pedal's name over mDNS for humans. The
  AP is always on, because "later joins don't ask" is the point, and its beacons and idling clients
  cost the render thread nothing measurable (the spike measures it rather than assuming).

### The three secrets, and what each is for

| Secret | Who holds it | What it proves | What it stops |
|---|---|---|---|
| The BLE bond (ASK) | the phone and the Pico | this phone is the owner's | a stranger's app being able to read the pedal's record at all |
| The network passphrase | the Pico (authoritative), the Core host (a derived cache), the app's keychain | this device may join the pedal's network | someone in radio range without the pedal's consent |
| The `namchaind` token | the Core host, and the app's keychain | this client may drive the engine | anything on the pedal's network that is not the app |

The passphrase is generated by the **Pico on first boot** and never by the Core host: the pairing
record belongs with the bonds, the BLE side has to be able to answer while the Core host is booting,
and the Pico is the part that is on from power-on. The record is `{ssid suffix, passphrase,
generation}`; the Core host keeps a **derived cache** so `hostapd` can start at boot without waiting
for the UART, and the two merge by generation (below). Nothing else copies it.

### The provisioning bundle

The one thing the app reads over BLE is a small JSON document — the pedal's answer to "how do I reach
you":

```json
{ "v": 1, "name": "Pedal-7F3C", "ssid": "Pedal-7F3C", "psk": "……24 chars……",
  "psk_generation": 3, "host": "10.77.0.1", "port": 47810, "token": "……namchaind's token……" }
```

- `ssid`, `psk`, `psk_generation` are the Pico's record. `host`, `port`, `token` come from the pedal
  service, sent over the UART at session start and held in the Pico's RAM, never written to flash.
- The token is the engine's existing one (`/etc/namchain/token`, via systemd's `LoadCredential`), so
  the app needs no new secret and no new credential, and rotating the token is still one thing on the
  host.
- The characteristic is **protected** (`ENCRYPTION_KEY_SIZE_16` in the GATT database, as the SDK's own
  `ble_wifi_provisioner` example does): reading it requires the bond, and a fresh read is what makes
  ASK's `.confirmAuthorization` meaningful. It is also only populated in setup mode or for an
  already-bonded phone.

### The flow

**First meeting.** ljoss's Add Pedal screen says what to do; the pedal is put in setup mode (a
gesture; the first five minutes after a factory-fresh boot, so a new pedal needs no gesture at all).
The Pico advertises the service UUID and the name. `showPicker` shows the sheet with the pedal's
picture. The tap pairs (LE Secure Connections, Just Works) and the app reads the bundle over the
protected characteristic; if the descriptor matched the SSID the system already knows it, otherwise
the app calls `finishAuthorization(for:settings:)` with `settings.ssid` from the bundle. Then
`joinAccessoryHotspot(accessory, passphrase: bundle.psk)`, and `namchaind` is reachable. The app
writes a `PairedPedal` record (accessory id, name, ssid, psk, generation, host, port, token) to the
keychain, and the pedal leaves setup mode.

**Later.** On launch (and on returning to the foreground, because of `joinOnce`) the app: joins the
accessory's network with the stored passphrase, connects to `namchaind` with the stored token. If the
join fails, the bundle had no token because the pedal was still starting, or `namchaind` answers
`unauthorized`, it re-reads the bundle over BLE — a bonded phone may connect for that at any time —
and retries once. Nothing is asked of the user. If the accessory is gone from
`ASAccessorySession.accessories` (revoked in Settings), the app says so and offers to pair again.

**Forgetting, rotating, and a second phone.** "Remove pedal" in ljoss: the app writes "forget me"
over BLE (so the Pico drops the bond), then `removeAccessory` (which deletes the system bond), then
forgets the record. The pedal's own gesture — a long press whose exact form comes with firmware v1 —
wipes every bond and **bumps the record's generation and generates a new passphrase**, which is the
revocation: the old phone has a stale passphrase and no bond to fetch the new one. A second phone is
added the same way as the first, in setup mode, and shares the passphrase; the pedal holds a small
number of bonds (the SDK's link-key store; a handful is plenty).

**The record's merge rule.** The Pico's record is authoritative and carries a generation. At session
start the Core host sends what it has; each side adopts the higher generation, and a side with no
record adopts the other's. A Pico reflash that clears its flash therefore does not change the pedal's
passphrase — the Core host hands it back — and a reimaged Core host learns it from the Pico. A
passphrase rotation is only ever the Pico's, and the Core host regenerates `hostapd.conf` and restarts
`hostapd` when it sees the generation move (a second or two of AP downtime, and only on a deliberate
action).

### Setup mode

Setup mode is the whole security boundary for a new phone, so it is explicit:

- it is a gesture on the pedal (with the display it also says so); a factory-fresh pedal allows it for
  its first five minutes instead, so the first meeting is easy;
- it lasts a short window (five minutes, proposed), and leaves when a phone pairs or the window ends;
- only in it does the Pico advertise the setup service and accept a new bond;
- the Pico's LED/panel says "pairing" while it is open — so a phone that pairs by accident is visible,
  and the gesture is never a surprise.

### The QR on the display (Phase 3.7, optional)

The display makes three things nicer, and none of them is on the critical path:

- **The Mac, and any non-iOS client.** A QR with the standard `WIFI:` payload is joined by the
  system Camera without ljoss; the display can also show the address, so the Mac's manual path needs
  no `ssh` to read the passphrase. (The token is still pasted or typed; it is already in the Mac's
  keychain today.)
- **An out-of-band check for the first pairing.** The pedal shows a short code and the app asks for
  it before it accepts the bundle; that closes the small window in which a stranger in BLE range
  could race the owner's tap. Worth doing when the display exists, not worth blocking on.
- **A fallback.** If ASK misbehaves on some iOS, the QR plus `NEHotspotConfiguration.apply` plus a
  typed token is the path that always works.

The QR is not in the bundle path (a 64-character token makes it unreadable at 240 px wide), and the
screens' contents rotate with the passphrase, not with every boot.

### What each side must build

| Where | What |
|---|---|
| `firmware/` | BTstack BLE peripheral: the GATT database (a `.gatt` file and `pico_btstack_make_gatt_header`, as the SDK examples do), the service UUID and name in the advertisement (name in the scan response if 128-bit UUIDs and the name do not both fit), the link-key store in flash, the record in flash, setup mode, the bundle, and the two new UART messages. `pico_btstack_ble` + `pico_btstack_cyw43` beside today's `pico_cyw43_arch_none`. The BLE side never touches audio, the relay or the rig |
| `devices/` | `wlan0` as the access point (a `pedal-ap` script and unit, `hostapd`, the static address, a DHCP server, mDNS), the state file and its permissions, the station path leaving the pedal root, and the rescue root's configuration unchanged |
| `pedald` | the provisioning fields to the Pico at session start; the record's merge; the new UART messages; nothing on the audio path |
| `docs/uart-protocol.md` | draft 3: `PROV` (Core → Pico: host, port, token; and the record in both directions for the merge) and `PAIR` (Pico → Core: setup mode entered/left, a phone paired, bonds wiped, the generation moved). The exact bodies are the doc's to settle; the Pico's BLE work is gated on them |
| ljoss | the Info.plist keys and the capability, a `Pairing/` group (the ASK session, the CoreBluetooth client for the bundle, the `PairedPedal` record and its keychain storage), the picker image from `enclosure/renders/`, the Add Pedal flow and the Hardware page, and the foreground re-join |
| `scripts/` | unchanged on the bench (Ethernet). Off the bench the pedal is only on its own AP, so `--host` becomes the AP's address, and the README says so; no script learns to speak BLE |

## Stages

Each lands on its own, and the first is spikes: the Apple half is the only part of this pedal that
cannot be tested from a shell, so it is retired before anything is built on it. Evidence goes in
`bench-results/pairing/`.

**0. Spikes.**
1. **The Core host as an access point.** `hostapd` + a static address + a DHCP server on `wlan0`, a
   fixed test passphrase, a Mac and a phone join, `namchaind` answers over it. Measure: boot to AP up;
   the render tail for an hour of playing while the app edits over the AP (the same gates as plan
   1.8); the AP's cost with the link idle.
2. **The Pico as an ASK-shaped peripheral.** A `bleak` script in `firmware/tools/` (the SDK's
   `ble_wifi_provisioner` is the reference) advertises, bonds, and reads a protected characteristic.
   Check: the advertising packet fits (UUID, name, flags); the Bluetooth address is the same across
   reboots, reflashes and a flash wipe (if it is not, it is set explicitly from the board's unique id
   and stored); a bond survives a reboot; a wiped bond store is detectable.
3. **The Apple half, on a real phone.** A throwaway ljoss screen (or a small test app) with the plist
   keys: the sheet shows the picture and name; the tap pairs; `joinAccessoryHotspot` joins spike 1's
   access point. Settle here: whether the descriptor's `ssidPrefix` is enough or the app must
   `finishAuthorization(settings.ssid)`; which `setupOptions` are needed; what happens to the
   association when ljoss is backgrounded (the 15 s rule) and when the phone is asleep; what the
   sheet looks like when the pedal is not in setup mode; whether the entitlement is granted on the
   owner's team. **If the join cannot be made to work, the design changes here**, to the QR path.
4. **The bench loop.** The Mac joins the pedal's AP and runs `scripts/status` and
   `sync-library --host <ap address>`; an upload of a model and an IR is timed.

**1. The pedal's own network** (`devices/`, `pedald`): the `pedal-ap` unit and script, the address
and DHCP, mDNS, the state file, the station path out of the pedal root, the image's secrets change,
the merge, and the two UART messages. Done when a card boots with the AP up, the AP comes back after a
`hostapd` restart and a passphrase rotation, the merge behaves on a Pico reflash and a reimaged Core
host, and Phase 1's soak gates still hold.

**2. The Pico's record, and setup mode** (`firmware/`): the record and bonds in flash, setup mode and
its window, the bundle and the protected characteristic, the forget gesture, and the counters the
panel will show. Done when the `bleak` script from the bench pairs, reads the bundle, and the pedal
survives a flash wipe with the Core host's cache.

**3. ljoss pairs** (ljoss): the plist keys and the capability, the ASK session and the picker with the
hero render, the bundle over CoreBluetooth, the join, the `PairedPedal` record, the Hardware page's
pedal section, the manual path kept for the Mac, and the foreground re-join. Done when a fresh phone
pairs with no typing, reconnects after a launch and after a background trip, and picks up a rotated
passphrase without asking.

**4. Lifecycle and the second factor** (with Phase 3.7's display when it exists): remove and rotate on
both sides; a second phone; the pedal's own forget gesture; `backup` and restore covering the Core
host's cache; the QR for the Mac and as the out-of-band check.

**5. Soak it.** An hour through the pedal's own AP with ljoss editing, a setup window opening and
closing, a phone backgrounded and returning, a passphrase rotation, and power pulled during a
rotation. The gates are Phase 1.8's, plus: no click when the AP restarts for a rotation, and the
pedal plays through every part of it.

**Done when:** a pedal and a phone that have never met pair with the system sheet and no typing; the
pedal plays from power-on on its own network with no house network anywhere; ljoss edits it over that
network; and the soak is clean.

## Failure modes to design for

| What happens | What must be true |
|---|---|
| The phone is backgrounded for more than 15 s | The association goes (`joinOnce`); the app re-joins on return, and the engine's rig keeps playing. ljoss already pauses when not active |
| The phone's Wi-Fi is off, or it is on another network | The app says which network to join, or offers the manual path; the pedal keeps playing with no app (D3) |
| The Core host is rebooting | The pedal's AP is down for the boot (~20 s). The Pico can still pair and hand over the network half of the bundle; the app's connect retries, and it re-reads the bundle for the token once the pedal answers |
| The Pico is reset or reflashed | The Core host's cache keeps the passphrase; bonds come back from the Pico's flash or the owner pairs again |
| The Core host is reimaged | It learns the record from the Pico; the app is unaffected |
| The token is rotated | The app's first connection is refused; it re-reads the bundle over BLE and retries once, then says so |
| The app is reinstalled | ASK's accessories may be gone; the app offers to pair again, and the pedal's stale bond is cleared by the pedal's gesture (the mismatched-keys case the SDK README warns about) |
| A stray phone in setup mode | The pedal's LED/panel says pairing; the window is short; the QR code (stage 4) is the real fix |
| Power is cut mid-rotation | The record is written before the generation is published, so the pedal comes back on one of the two, never on neither |

## Risks, honestly

- **ASK's opaque corners.** The SSID/`finishAuthorization` shape, the `.confirmAuthorization` pairing,
  and what the sheet does when the pedal is bonded elsewhere are all learnable only on a device. The
  spikes exist for these, and the QR path is the fallback that needs none of them.
- **`joinOnce`'s 15 seconds** is a behaviour, not a bug, and it shapes the app: the association is
  re-made per foreground session. It also means the owner's phone is not silently parked on the
  pedal's network, which is the good half of the same rule.
- **The Pico's Bluetooth address** must be stable or the bond is worthless; the SDK's README warns
  that a flash wipe can move it. Spike 0.2 settles it, and the fix (set it from the board's unique id)
  is small.
- **The AP is the only way in.** With the pedal sealed and away from the bench there is no Ethernet, so
  a broken `hostapd` means no app and no `ssh` — the rescue root's station and the card reader are the
  recovery, and the pedal plays regardless.
- **The pedal has no clock without a network**, and never had one: no RTC battery in the pedal, and
  the Pico has no RTC either. Nothing in the pedal needs wall-clock time today, but if it starts to,
  the cheap fix is the app handing the pedal the time over BLE, and it should be said here rather
  than discovered later.
- **The Mac is a second-class citizen.** ASK is iOS-only. The Mac keeps a typed address and token
  until the display's QR exists, and that is acceptable for the owner's bench.

## Open, and deliberately not settled here

- Whether the pedal's AP should be able to be switched off from the panel, for a player who does not
  want the SSID around (a preference, not a requirement).
- Whether a second *pedal* on one phone should be supported from the start (the app's record is a
  list, so it is nearly free) and how two pedals would be told apart in the picker.
- The exact gesture for setup mode and for forget-all, which belongs with the panel work (3.5/3.7).
- Whether the Pico as access point is worth revisiting after spike 0.1 measures the Core host's AP
  properly. **Yours.**
- Whether the QR's out-of-band code is worth the camera permission before the display exists. It is
  not needed; it is the strongest answer to "how do I know this is my pedal?". **Yours.**

## The decisions this asks of you

| # | Question | Proposal |
|---|---|---|
| P1 | Who runs the access point? | **The Core host.** The Pico cannot route IP; the Pi's `hostapd` path is proven and already carries the app's traffic. The Pico keeps BLE |
| P2 | How does the app learn the passphrase? | **Over BLE, from a protected characteristic, only in setup mode or to a bonded phone.** No QR, no typed code, nothing to photograph |
| P3 | Does the first pairing need an out-of-band check? | **Not for v1.** The physical setup gesture and the short window are the boundary; the display's code is the upgrade when the display exists |
| P4 | What happens to the pedal's home network? | **The pedal's own network replaces it.** The pedal root drops the station path; the bench uses Ethernet, and the rescue root keeps its station |
| P5 | Does the app get the `namchaind` token over BLE? | **Yes**, in the same bundle, held in the Pico's RAM only. One secret for one appliance, no second credential and no typed token |
