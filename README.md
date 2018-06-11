# CloudCIX Robot

Our little Robot script that is the backbone of the CloudCIX project, and handles the building of infrastructure.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes. See deployment for notes on how to deploy the project on a live system.

### Prerequisites

- Some form of Linux (inotify lib doesn't run on Mac or Windows)
- python3.6 or later

### Installing

Firstly, install the requirements

```bash
sudo pip3 install -r deployment/requirements.txt
```

Run with the following command:

```bash
CLOUDCIX_SETTINGS_MODULE=settings python3 robot.py
```

## Running the tests

Currently don't have tests. Maybe we could come up with some?

## Deployment

The `deployment` directory contains ansible-playbooks that will deploy the system for us to different servers so there's no need to worry