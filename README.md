# Cellscan

Cellscan is a small software package intended to run on an embedded computer with specific hardware attached. It continuously collects information on nearby cellular base stations and periodically submits that information to a collection server. The information can then be analyzed using various heuristics to detect likely use of IMSI catcher devices (commonly called Stingrays after one such device) used for covert surveillance.

**This is very much a work in progress and I continue to work on both stability improvements and features.** However, it is currently at "MVP" stage and installed in my truck. The current data collection server is extremely basic and I am working on a better implementation which will be available here shortly.

## Origins

This project is loosely based on Project Seaglass from the University of Washington, but with the goal of using a significantly lower cost and easier to obtain data collection segment. The major differences from Seaglass are:

- Use of a different model of cellular model that's much easier to buy (in fact almost comically easy to buy)
- Use of the same cellular modem used for data collection to submit the data, avoiding the need for a separate LTE hotspot but complicating the software a bit.
- Designed with low cellular data usage in mind, to allow the use of a low-cost bill-by-MB "IoT" cellular plan
- Use of the cellular modem's built-in GNSS (GPS/GLONASS) capability for location tracking instead of a dedicated serial GPS receiver.
- Elimination of the "bait phone," more discussion of this later.
- Much simpler, more compact, and lower cost power supply arrangements.

The total cost of my hardware design is about $160 and some labor. Using an IoT provider like Hologram, cellular service should be less than $10 per month per unit.

# Make It Work

## Required Hardware

I would like this to be as easy to run as possible. However, the vast majority of cellular basebands are limited to reporting detailed information on the current associated cell and less complete information on neighbor cells. Obtaining detailed information on *all* nearby cells requires hardware with a special feature exposing this information. So far, the only vendor I have found that offers such a capability is Telit, in their IIoT-oriented data modems.

Project Seaglass also uses a Telit modem, which first made me aware of their unique "Easy Scan" feature. However, the specific serial-interface Telit modem used by Project Seaglass is quite expensive and rather difficult to obtain. Fortunately, I found that Telit manufactures a modem with the same feature in a standard Mini-PCIe form factor and that, even more fortuitously, it is resold in single units by Raspberry Pi IoT accessory vendor SixFab.

So, that preamble complete, here is my bill of materials in roughly descending price order. Most of these are pretty interchangeable but you do specifically need a Telit modem.

- Telit LE910C1 Mini PCIe LTE CAT1 Module, $55 @ SixFab
- SixFab 4G/4G & LTE Base Hat, $39 @ SixFab
- Raspberry Pi 4B, 2GB RAM, $35 @ Adafruit
- Heatsink for RPi recommended, a few $ @ Adafruit
- "Ultra-Small DC-DC Step-Down Module 3A" (catalog UDC-6), $2.90 @ All Electronics
- Bingfu puck LTE/GPS antenna, $23.99 from Amazon. Many other options available, but a three-element antenna (GPS, LTE main, LTE diveristy) is recommended. Otherwise two separate LTE monopoles and a GPS patch antenna could be used.
- Enclosure of choice, such as MB-742 from All Electronics (7.8x4.9x1.6" ABS plastic)
- Cabling and hardware for power supply, I used a cigarette lighter plug w/ 6' cord to which I attached a DC barrel connector, and a panel-mount DC barrel jack on the enclosure.
- Hardware to get the antenna connected. The Telit module has u.FL connectors and most external antennas will have SMA or RP-SMA. u.FL to SMA pigtails are easy to buy online.
- A few commodity electronic parts, I have a toggle switch on the 12V power, push button, LED, panel-mount holder for LED, resistor for LED. Currently the software expects a button between GPIO 4 and ground and an LED on GPIO 18. These should probably be configurable in the future.
- Some single-pin female header connectors are a nice way to connect power and things to the rpi header.

Full assembly instructions still need to be written but if you tinker with electronics you can probably figure it out from that list. A couple of notes:

- I am not using the SixFab LTE base as a hat at all, I'm using it purely as a USB device. Mostly this just makes packing things into my enclosure easier. If you do have it on the RPi expansion header as a "hat" you gain some features like being able to hard reset it and put it into low power mode via GPIO, but the software doesn't currently use any of these. Although you could connect it by UART this software currently requires that it be connected by USB so that we can use the multiple USB serial devices it exposes to get a dedicated NMEA feed.
- The "ultra-small DC-DC step down module" mentioned is indeed uncomfortably small but seems to manage the load without overheating. All Electronics is a surplus type deal and it may not be available in the future, in general just get some kind of 12v to USB or 5v power adapter, but it should probably be rated for at least 2A. In any case using an inverter, plug tee, and several power bricks like the project seaglass people is just insanity.
- I sometimes run mine off of a small SLA battery for testing (replaced UPS battery). This keeps it going for a while so you could totally use it in a backpack or on a bike if you wanted to.

## Computer Setup

Assuming you are using a Raspberry Pi and Raspbian, there are some system setup steps you will need to take:

- Tell dhcpcd not to manage the cellular modem or it will keep messing with things. Do this by adding "denyinterfaces wwan0" to /etc/dhcpcd.conf.
- Install ModemManager, but do *not* install NetworkManager.
- Install this Python module and 'cellscan' should end up in the $PATH. Use the provided systemd unit file to have it start on boot. Cellscan should run as root because it needs to manage interfaces and routes and such.