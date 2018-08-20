# CloudCIX Robot

Our little Robot script that is the backbone of the CloudCIX project, and handles the building of infrastructure.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes. See deployment for notes on how to deploy the project on a live system.

### Prerequisites

- Docker

### Installing

Download the Alpha container from the registry;

```bash
docker pull gitlab.cloudcix.com:5005/cloudcix/robot:alpha
```

You can load local code into the container using the `-v` flag.

Robot's code is stored in `/opt/robot` on the container.

## Running the tests

Currently don't have tests. Maybe we could come up with some?

## Deployment

The `deployment` directory contains ansible-playbooks that will deploy the system for us to different servers so there's no need to worry
