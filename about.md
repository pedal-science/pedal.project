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

## Initial state

My current design draft uses the following hardware (that I already own). N.B. the names "Core", "HumanInterface" and "Codec" are ones I've just coined for this doc to make it easier to refer to them:

* "Core" - an ASUS Tinkerboard - for processing-intensive work (effects processing).
* "HumanInterface" - A board similar to a Pi Pico - for user input and output interfacing, to allow the Core to concentrate on its ojb.
* "Codec" - A WM8960 based stereo audio codec breakout board - for audio hardware interfacing.
* Power supplies that can supply adequate, clean input.
* A spare pedal case that is large enough to house the ....hardware
* A tiny (2.4") TFT screen with a couple of control inputs also on the board (a rotary encoder and a button). N.B. Adding a screen like this is low priority.

I am planning to use the following software that I've been working on:

* On the Tinkerboard:
    * A tweaked Armbian build, adding RT support to the kernel and providing runtime isolation for running effect processing code. This exists at https://github.com/rikkus/rtpi
    * A code library whose job is to handle the processing-intensive realtime work - the processing of audio data, applying effects. The project has recently had a draft daemon wrapper added. It is at http://github.com/rikkus/namchain

* Outside of the pedal:
    * 'ljoss', a SwiftUI application that runs on MacOS and iOS. This is a rig designer. It sends rigs - ready for running - to namchain (it's wired up to speak to namchaind over TCP). It's here: http://github.com/rikkus/ljoss

## Some (and only some) of the pending work

* I haven't tried connecting the Pico-alike board to anything. I don't have any experience with using such a board and I don't know how it should be programmed so that it works as hoped.

* The way that namchain and ljoss communicate is very draft. It works, but there's a lot to consider and perhaps some design changes needed as it's refined.

## Design decisions

* The primary interface for this pedal will - initially - be the app. I'd rather get the pedal working enough to play guitar through than trying to get footswitches, MIDI input, other hardware controller input or inbuilt display output working. N.B. I said 'rather'. I've made the assumption here that - especially given my lack of experience with hardware project in general - I would find it frustrating to be working on things that don't get the thing up and running with guitar input, effects processing and audio output all working.

## Open questions

* If I decide I want to add rig design support for more platforms, what's best?
    * Write a Qt-based designer
        * And deprecate the SwiftUI & Swift implementation
        * Or add it as a second implementation
    * Something else?

* Should any of the software or hardware design decisions be re-visited?
* Should any of the software implementation decisions be re-visited?

## Notes

I have developed my own optimisations for NAM model processing. I created a repo to help me bring together my work in this area, which is at https://github.com/rikkus/NAMBench ... it may not be needed directly for work on this project, but I don't want it to be overlooked if there's point where it may be useful.

## Other resources

I'm currently planning to use my M2 Macbook Air (named 'M2') as the primary device for interacting with AI harnesses (Claude Code / Cursor / DeepSeek Harness) when working on this project. The reason for this is that any work on the rig designer requires interaction with MacOS, while work on the other software components can be done on M2 and sent to / executed on the Tinkerboard.

The Tinkerboard is named 'tib' and is available over ssh.
I also have a Raspberry Pi 500 named 'piv', which is also available over ssh.

piv and tib are (so far) always on my home network.

piv can be used for building, testing, etc. It's designed to be a do-everything utility server. It doesn't run anything critical, so if it is busy or down, it's not a problem.

tib can be used at will - it's the target for "Core" and it's not normally doing anything else. Sometimes I may do some work separately from this project (likely on its subprojects) - e.g. I've recently been working on potential optimisations to the IR code that's used in the reference NAM 'Core' code. I've been running benchmarks on tib as part of this, so any agent working with tib should expect the occasional small change that's not been seen previously, but should not expect me to be running benchmarks on it from elsewhere while also interacting with an agent working on this project.

