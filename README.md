# CloudCIX Robot

This project is the backbone of the CloudCIX project, handling deployment of infrastructure.
Robot is built entirely on top of [celery](http://www.celeryproject.org/), using `beat` to handle the periodic tasks, and `workers` to handle the actual infrastructure jobs.
Familiarising yourself with celery is recommended when attempting to work on Robot.

## Architecture

Robot itself is split into two major parts, both run by celery;

1. `celery beat`
    - This part of Robot handles periodic tasks.
    - Robot has two main periodic tasks;
        - `mainloop`, which runs every 20 seconds, sends requests to the API for requests to build, quiesce, restart and update infrastructure, and passes appropriate tasks to the workers
        - `scrub_loop`, which runs once a day at midnight, does the same except only looks for infrastructure that is ready to be completely deleted, and passes scrub tasks to the workers
2. `celery worker`
    - Each robot has potentially multiple worker containers deployed with it, which handle running the actual infrastructure tasks asyncronously from the mainloop

## Celery Setup

Some things to take note of regarding our set up for Celery;

- `-Ofair` causes celery to distribute tasks to workers that are ready, not as soon as they are received. This means workers that get short running tasks can handle the next task as soon as they are done, instead of piling work onto a worker that is running a long job [see here](https://medium.com/@taylorhughes/three-quick-tips-from-two-years-with-celery-c05ff9d7f9eb)

## Flower
Accessing the IP of the Robot host in the browser will give you access to the Flower instance for the region.

This provides a web UI for monitoring the tasks, queues and workers in Celery for the region.