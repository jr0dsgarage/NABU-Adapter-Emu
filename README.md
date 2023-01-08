# NABU Adaptor Emulator ![GitHub](https://img.shields.io/github/license/jr0dsgarage/Nabu-Adapter-Emu)

Standing on the backs of giants, I'm using this repository to learn and practice my python skills,
and to better understand the `NABU-PC <-> NABU-ADAPTOR <-> NABU-NETWORK` connection works,
while also trying to expand my understanding of the VSCode github workflow.

## jrodsgarage changes

- added logging and formatted the output, while doing a bit of work to properly structure the code, without changing functionality.
- added code to determine OS (Linux & Windows) and use the appropriate default syntax for opening the serial connection.  

*Everything below this line is inherited from the fork I forked this from*

---


## NABU-Loader

A heavily modified fork of https://github.com/mdebreceni/nabu-pc-playground

This is a Python program that takes the place of the NABU Network Adapter to load code into a NABU PC from a directory of pak files. Works with unmodified (but decrypted) files from the original NABU network, both cycle 1 and 2. It has also been updated to work with the encrypted cloud.nabu.ca files directly off the Internet.

As of 12/30/2022 I have written code to paketize and send a raw .nabu file. Now you can load and send a .nabu file from local disk with the -n option.

I used a lot of the code from mdebreceni's original but have modified it so much that it made sense to set this up as a fork for now. I also learned about the structure of the time segment and built the CRC algorithim from reading the C# code in GryBsh's network emulator project: https://github.com/GryBsh/NabuNetworkEmulator . Decryption code was found on a VCF forum post, which enabled me to support the cloud service directly.

Apologies in advance for bad code - is there a better way to do this? Sure, very probably. I'm doing what I can with what I know and have been able to learn. I do not consier myself to be a programmer. I'm doing this because it's fun and it's also teaching me a lot about Python.

So far, everything is working pretty well. There's a lot I still want to implement, but I think this is complete enough and functional enough to put up for others to look at and play with. Maybe consider this the beta for version 0.01. :)

NABU it to it!
