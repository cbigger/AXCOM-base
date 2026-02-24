# Agent XMPP Commander |  A X C O M
Build, deploy, manage, and command AI agents via XMPP.

## Overview
AXCOM is a set of tools for agent swarm creation and communication over [XMPP](https://xmpp.org/about/technology-overview/). It is written primarily in Python and is meant to be both AI agent and XMPP client agnostic.
AXCOM agent services can be run as a child process of the `controller` script/service, or they can be spawned into their own containers.

## TO-DO
1. systemd daemonization -- Need to make the unit file and update (or create a separate) install script and service paths.
2. Packaging tools for creating agent container images

## Requirements
This early version is built and tested on Debian virtual machines. 
Similarly, the current installation scripts are written for Debian, but can be adapted easily for other Linux distributions.
If you make use of the bootstrap and the install-docker scripts then the only thing that needs to be installed independently is Python,
which is generally packaged with most Linux distributions anyways. This makes this project easy to setup and run on virtual machines.

The basic requirements are:
1. Python3.13+ with slixmpp, dotenv,and openai (optional, used by built-in mini-agent)
2. python-pip -- Included as a dependency because it is used by the installation and agent container scripts
3. python-venv -- The systemd service runs under its own virtual environment
4. [Prosody IM](https://prosody.im/) -- This is one of two well known open source xmpp server applications, and supports custom plugins via lua-based module scripts
5. [Docker](https://docs.docker.com/engine/install/debian/) -- Technically optional, but a major component of the platform's intended use and direction. Used to spawn agent containers. Installing docker-ce requries a few steps, and they've been added in their own `install-docker.sh` script for debian systems

## Installation
You can easily install AXCOM by running the bootstrapping script, which will install prosody, python-pip, and python-venv before running the install.sh script itself:
```
sudo bash bootstrap.sh
```

If you already have those three packages installed, then you can simply run the installation script directly:
```
sudo bash install.sh
```

Once the installation is complete, a `.env` file will have been created in the project root. This file contains the passwords
for the **operator@localhost** and **controller@localhost** accounts. If you want to set your own password for these files
instead of using the (likely far safer) generated ones, see [Configuration](#Configuration) 

To get the most out of AXCOM, you will want to have [Docker](https://docs.docker.com/engine/install/debian/) installed as well. A docker-ce installation script for Debian is included, and can be run with:
```
sudo bash install-docker.sh
```
You can confirm docker is running with (or any other docker command, really):
```bash
sudo docker ps
```
Unless you already had docker installed and containers running, this should return an empty table.

## Usage
At the moment, I'm still building out the framework. A PoC for agent communication is included, but the main focus after daemonization is the addition of tools to create AXCOM agent images out of popular agent applications (like the Claw family, Claude Code, etc.).

You can start the controller bot like this:
```bash
source AXCOM-base/.venv/bin/activate
cd controller
python controller.py
```
You should see output confirming successful connection and login to your prosody Virtual Host "localhost".
You can then login to the localhost server using your XMPP client of choice with the username `operator` and the password found in the `.env`.


## Configuration
Unless you know what you are doing, there isn't any reason to edit the `config.toml` file found in the project root. AXCOM will fill it out during install as needed, and the agent builder and controller bot will use it to setup connections.

If you *do* know what you are doing, then you probably already noticed that the `config.toml` is where you can make changes to the Prosody server and file install locations, and where the docker tools write to.
