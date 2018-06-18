# python
import multiprocessing as mp
import sys
import time

# local
import dispatcher
import metrics
import ro
import settings
import utils


robot_logger = utils.get_logger_for_name('robot.mainloop')


def mainloop(process_pool: mp.Pool):
    """
    The main loop of the Robot program
    """
    last = time.time()
    while True:
        metrics.heartbeat()
        # Now handle the loop events
        # #################  VRF BUILD ######################################
        vrfs = ro.service_entity_list('IAAS', 'vrf', params={'state': 1})
        if len(vrfs) > 0:
            for vrf in vrfs:
                robot_logger.info(f'Building VRF with ID {vrf["idVRF"]}.')
                dispatcher.dispatch_vrf(vrf, settings.NETWORK_PASSWORD)
        else:
            robot_logger.info('No VRFs in "Requested" state.')
        # ######################## VM BUILD  ################################
        vms = ro.service_entity_list('IAAS', 'vm', params={'state': 1})
        if len(vms) > 0:
            for vm in vms:
                robot_logger.info(f'Building VM with ID {vm["idVM"]}')
                # Until we know VM dispatch works, keep it synchronous
                dispatcher.dispatch_vm(
                    vm,
                    settings.NETWORK_PASSWORD,
                )
                # Call the dispatcher asynchronously
                # try:
                #     process_pool.apply_async(
                #         func=dispatcher.dispatch_vm,
                #         kwds={
                #             'vm': vm,
                #             'password': settings.NETWORK_PASSWORD
                #         }
                #     )
                # except mp.ProcessError:
                #     robot_logger.error(
                #         f'Error when building VM #{vm["idVM"]}',
                #         exc_info=True
                #     )
        else:
            robot_logger.info('No VMs in "Requested" state.')

        while last > time.time() - 20:
            time.sleep(1)
        last = time.time()


if __name__ == '__main__':
    # When the script is run as the main
    current_commit = utils.get_current_git_sha()
    # Log the current commit to both the file and InfluxDB
    robot_logger.info(
        f'Robot starting. Current Commit >> {current_commit}. '
        f'ROBOT_ENV={settings.ROBOT_ENV}',
    )
    if settings.ROBOT_ENV != 'dev':
        metrics.current_commit(current_commit)
    # Create a pool of workers equal in size to the number of cpu cores on the
    # server
    mp.set_start_method('fork')
    pool = mp.Pool(
        processes=None,
        maxtasksperchild=1,
    )
    rc = 0
    try:
        mainloop(pool)
    except KeyboardInterrupt:
        # Going down safely
        pass
    except Exception:
        robot_logger.error(
            'Exception thrown in robot. Exiting.',
            exc_info=True,
        )
        rc = 1
    finally:
        metrics.heartbeat(0)
        pool.close()
        pool.join()
        sys.exit(rc)
