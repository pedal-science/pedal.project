# NAM A2 amps in Fractal VP4

A project by Marco Bricole. Here's Marco's post:

The Fractal VP4 is a little marvel: four studio-quality effects in an enclosure the size of a single pedal. But it’s missing one thing, it doesn’t model amps. So you always need a real amp behind it, or another modeler. Hence the slightly crazy idea: what if we ran a NAM (Neural Amp Modeler) model directly inside the VP4?

Until recently that was out of reach for a small microcontroller. Running a neural network in real time is heavy number crunching, the kind of thing reserved for a PC or a dedicated pedal DSP. Two things changed. First the Teensy 4.1, which packs a 600 MHz Cortex-M7 with a floating-point unit and, above all, zero-wait-state internal SRAM, the memory that sits right against the core, essential when you have to put out a sample every 20 microseconds. Second and most importantly, the new A2 architecture released by Steven Atkinson, the creator of NAM: for equivalent capture quality, it requires far fewer operations per sample than the older WaveNet Standard models. That’s what moves the computation from “impossible” to “fits comfortably within the CPU budget.”
So I slipped a Teensy 4.1 into the enclosure using a four-cable method (pseudo, since I pick up the digital signal directly), and the code is now finished. The thing is, I don’t go back out through jack sockets: I tap the audio directly in the digital domain at the VP4’s audio converter, the Cirrus CS4272 codec, by listening in on its I2S bus. The Teensy locks onto the VP4’s clock and reads the stream as is. No pointless analog conversion, no added hiss, no second clock domain, no extra latency at this stage.
That’s also what should preserve the dynamics. Every analog round trip costs you noise: one converter going back down to analog and another coming back up to digital stacks two noise floors and shaves off a few dB at each pass. Here there are none. I grab the 24-bit samples already converted by the DSP for the CS4272, the processing is done in 32-bit floating point, and the only real analog link left is the output. So we should stay around 112 dB of dynamic range, in other words at the level of the VP4’s original converter. The processing degrades nothing.
On the model side, the NAM files live on the Teensy’s SD card, which can hold an enormous number of them. Selection, however, is currently limited to 128 different models, simply because a MIDI CC message only carries a value from 0 to 127. That’s already plenty, and it can evolve later.
The VP4 itself drives everything, over MIDI: when you load a preset, it sends four Custom Scene MIDI messages telling the Teensy which models to fetch from the SD card. All four are loaded into fast internal memory at once. Then, on each scene change, the VP4 sends a simple sync CC and the Teensy switches from one model to another with a pointer swap. No reloading, nothing to read back from the SD card.
The code is finished and the logs are clean: no dropped blocks, no processing overruns. I get stable behavior with headroom in the CPU budget (55% to 65% depending on which of the two types of fast memory the model sits in), even though the four models take up roughly 95% of the available fast memory. It’s tight, but it works. Amp switching happens in about 1.3 ms, in other words inaudible, with no gap in the sound. And the audio latency of the chain stays under 1 ms (block processing, 16 samples at 48 kHz), which is less time than it takes sound to travel 30 cm through air.
Edit : I made a PCB board to reduce the number of wire. I've made the JLPCB order.  

## Discussion

Andrea Posarelli: Interesting. How you control the Nam loader?
Marco Bricole: vp4 can send 5 midi messages per scene One is the message for the button pressed and 4 are specific to a scene and a preset so 128 possibilities of amp per scene and per preset. The switch between the 4 amps of a preset is 1.3 ms max.

Nick Johnson: I have no idea what I just read, but my pea sized intellect deduced you added amp/cabs to your VP4?
Marco Bricole: Exactly. The amps are running on the NAM A2 algorithm loaded on a microcontroller. Added latency is under 1 ms.

Carmelo Di Lio: I guess it's fixed either pre or post fx, right?
Marco Bricole: The amps are running where th 4CM block is placed. I put it after the 2 effetx block and before delay and reverb but any possibility is possible with vp4
