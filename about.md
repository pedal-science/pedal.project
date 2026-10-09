# Pedal Project

## About

This is a guitar / bass / vocals effects pedal project.

## Goal

A single working pedal, for my own use, with the following attributes:

* Entirely digital effects.
* Uses a rig specification document to create a virtual rig.
* Supports input from an external MIDI controller.
* Very low noise (clean audio paths).
* Supports NAM models.
* Supports IR.
* Immune (as far as practical) from undesirable audio artefacts such as glitches, pops and dropouts.

## Non-goals

* Support everything that other systems do. For example: I don't currently have any opinion about supporting standard effects plugins such as AUv3, so I don't have a goal of supporting them. That does NOT mean that I won't want to in the future, however, I just haven't given enough thought to the subject yet.

## Constraints

* Re-use the hardware I have already if it's suitable.

## Design principles

The principles that shape the physical design, and the reasoning behind them.

* **Robustness.** This is a guitar pedal: it will be dropped, kicked and abused in various other ways. It should have a level of protection against failure.

* **Case size.** Space inside the case is limited necessarily - a pedal that is much bigger than it really needs to be is less practical to use. It takes up more space on the floor, and it is higher than it should be. Players expect the footswitches in a particular range of height from the floor, so a pedal that's higher than they expect could lead to a mis-stomp.

* **Placement inside the case.** Design choices affect placement within the case. Reduced placement choices means less room (no pun intended) for heat management and less ability to create separation between components where that is desirable.

## Hardware

The design uses the following hardware. N.B. the names "Core", "HumanInterface" and "Codec" are ones I coined for this doc to make it easier to refer to them:

* "Core" - a Raspberry Pi 5 (1 GB), named 'vip' - for processing-intensive work (effects processing).
* "HumanInterface" - a Raspberry Pi Pico 2 W - for user input and output interfacing, to allow the Core to concentrate on its job.
* "Codec" - A WM8960 based stereo audio codec breakout board - for audio hardware interfacing.
* Power supplies that can supply adequate, clean input.
* A 1590DD-size pedal case (188 x 119 x 37.5 mm).
* A 2.4" ST7789 TFT screen with a couple of control inputs also on the board (a rotary encoder and a button). N.B. Adding a screen like this is low priority.

I am planning to use the following software that I've been working on:

* On the Core host:
    * `rtpi` - the Core host's kernel and boot configuration: a realtime (PREEMPT_RT) kernel, boot slots that fall back safely, and the isolation of the cores that run effect processing. This exists at https://github.com/rikkus/rtpi
    * `namchain` - a code library whose job is to handle the processing-intensive realtime work - the processing of audio data, applying effects - plus `namchaind`, the daemon that renders the rig and drives ALSA directly. It is at http://github.com/rikkus/namchain

* Outside of the pedal:
    * 'ljoss', a SwiftUI application that runs on MacOS and iOS. This is a rig designer. It sends rigs - ready for running - to namchain (it's wired up to speak to namchaind over TCP). It's here: http://github.com/rikkus/ljoss

## Some (and only some) of the pending work

* The Pico side has moved on since I wrote this: the firmware links to the Core host over UART and the protocol is bench-tested. What isn't built yet is the physical side - footswitches, MIDI in, LEDs and the display.

* The way that namchain and ljoss communicate is very draft. It works, but there's a lot to consider and perhaps some design changes needed as it's refined.

## Design decisions

* The primary interface for this pedal will - initially - be the app. I'd rather get the pedal working enough to play guitar through than trying to get footswitches, MIDI input, other hardware controller input or inbuilt display output working. N.B. I said 'rather'. I've made the assumption here that - especially given my lack of experience with hardware project in general - I would find it frustrating to be working on things that don't get the thing up and running with guitar input, effects processing and audio output all working.

## Open questions

* If I decide I want to add rig design support for more platforms, what's best? *(2026-10-09, D14: a Qt 6 UI, rigpa, runs on the pedal itself beside ljoss; ljoss stays the Mac/iOS designer.)*
    * Write a Qt-based designer
        * And deprecate the SwiftUI & Swift implementation
        * Or add it as a second implementation
    * Something else?

* Should any of the software or hardware design decisions be re-visited?
* Should any of the software implementation decisions be re-visited?

## Notes

I have developed my own optimisations for NAM model processing. I created a repo to help me bring together my work in this area, which is at https://github.com/rikkus/NAMBench ... it may not be needed directly for work on this project, but I don't want it to be overlooked if there's point where it may be useful.

## Other resources

I'm currently planning to use my M2 Macbook Air (named 'M2') as the primary device for interacting with AI harnesses (Claude Code / Cursor / DeepSeek Harness) when working on this project. The reason for this is that any work on the rig designer requires interaction with MacOS, while work on the other software components can be done on M2 and sent to / executed on the Core host.

The Core host is named 'vip' - a Raspberry Pi 5 (1 GB) - and is available over ssh.
I also have a Raspberry Pi 500 named 'piv', which is also available over ssh.

vip and piv are (so far) always on my home network.

piv can be used for building, testing, etc. It's designed to be a do-everything utility server. It doesn't run anything critical, so if it is busy or down, it's not a problem. It stood in as the Core host before vip arrived, and keeps its own dev checkouts.

vip is the target for "Core" and is where the pedal is being tested, so I want to keep it quiet and shared: it never builds anything (builds happen on M2), only one measurement runs at a time, and nothing heavy should start on it without asking first.

