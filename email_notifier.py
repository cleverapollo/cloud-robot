"""
class with static methods that handles sending emails from different tasks on successes or failures
"""
# stdlib
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from json import dumps
from typing import Any, Dict
# local
import settings
import utils

__all__ = [
    'EmailNotifier',
]


class EmailNotifier:
    # A list of image files that need to be attached to the emails
    message_images = ['logo.png', 'twitter.png', 'website.png']

    # ############################################################## #
    #                               NOC                              #
    # ############################################################## #

    @staticmethod
    def failure(vm_data: Dict[str, Any], task: str):
        """
        Report any kind of failure to the NOC and developers emails
        """
        logger = logging.getLogger('robot.email_notifier.failure')
        logger.debug(f'Sending failure email for VM #{vm_data["idVM"]}')
        # Add the pretty printed data blob to the VM
        vm_data['data'] = dumps(vm_data, indent=2, cls=utils.DequeEncoder)
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/failure.j2').render(
            compute_url=settings.COMPUTE_UI_URL,
            task=task,
            **vm_data,
        )
        # Format the subject
        subject = settings.SUBJECT_PROJECT_FAIL
        EmailNotifier._compose_email(settings.SEND_TO_FAIL, subject, body)

    @staticmethod
    def vrf_failure(vrf_data: Dict[str, Any], task: str):
        """
        Report any kind of failure to the NOC and developers emails
        """
        logger = logging.getLogger('robot.email_notifier.vrf_failure')
        logger.debug(f'Sending failure email for VRF #{vrf_data["idVRF"]}')
        # Add the pretty printed data blob to the VRF
        vrf_data['data'] = dumps(vrf_data, indent=2, cls=utils.DequeEncoder)
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/vrf_failure.j2').render(
            compute_url=settings.COMPUTE_UI_URL,
            task=task,
            **vrf_data,
        )
        # Format the subject
        subject = settings.SUBJECT_VRF_FAIL
        EmailNotifier._compose_email(settings.SEND_TO_FAIL, subject, body)

    # ############################################################## #
    #                              BUILD                             #
    # ############################################################## #

    @staticmethod
    def build_success(vm_data: Dict[str, Any]):
        """
        Given a VM's details, render and send a build success email
        """
        logger = logging.getLogger('robot.email_notifier.build_success')
        logger.debug(f'Sending build success email for VM #{vm_data["idVM"]}')
        # Check that the data contains an email
        email = vm_data.get('email', None)
        if email is None:
            logger.error(f'No email found for VM #{vm_data["idVM"]}. Sending to {settings.SEND_TO_FAIL} instead.')
            email = settings.SEND_TO_FAIL
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/build_success.j2').render(
            compute_url=settings.COMPUTE_UI_URL,
            **vm_data,
        )
        # Format the subject
        subject = settings.SUBJECT_VM_SUCCESS
        EmailNotifier._compose_email(email, subject, body)

    @staticmethod
    def vrf_build_success(vrf_data: Dict[str, Any]):
        """
        Given a VRF's details, render and send a build success email
        """
        logger = logging.getLogger('robot.email_notifier.vrf_build_success')
        logger.debug(f'Sending build success email for VRF #{vrf_data["idVRF"]}')
        # Check that the data contains an email
        email = vrf_data.get('email', None)
        if email is None:
            logger.error(f'No email found for VRF #{vrf_data["idVRF"]}. Sending to {settings.SEND_TO_FAIL} instead.')
            email = settings.SEND_TO_FAIL
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/vrf_build_success.j2').render(
            compute_url=settings.COMPUTE_UI_URL,
            **vrf_data,
        )
        # Format the subject
        subject = settings.SUBJECT_VPN_SUCCESS
        EmailNotifier._compose_email(email, subject, body)

    @staticmethod
    def build_failure(vm_data: Dict[str, Any]):
        """
        Given a VM's details, render and send a build failure email
        """
        logger = logging.getLogger('robot.email_notifier.build_failure')
        logger.debug(f'Sending build failure email for VM #{vm_data["idVM"]}')
        # Check that the data contains an email
        email = vm_data.get('email', None)
        if email is None:
            logger.error(f'No email found for VM #{vm_data["idVM"]}. Sending to {settings.SEND_TO_FAIL} instead.')
            email = settings.SEND_TO_FAIL
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/build_failure.j2').render(
            compute_url=settings.COMPUTE_UI_URL,
            **vm_data,
        )
        # Format the subject
        subject = settings.SUBJECT_VM_FAIL
        EmailNotifier._compose_email(email, subject, body)

        # Also run the generic failure method to pass failures to us
        EmailNotifier.failure(vm_data, 'build')

    # ############################################################## #
    #                             QUIESCE                            #
    # ############################################################## #

    @staticmethod
    def delete_schedule_success(vm_data: Dict[str, Any]):
        """
        Given a VM's details, render and send a delete_schedule success email
        """
        logger = logging.getLogger('robot.email_notifier.delete_schedule_success')
        logger.debug(f'Sending delete scheduled email for VM #{vm_data["idVM"]}')
        # Check that the data contains an email
        email = vm_data.get('email', None)
        if email is None:
            logger.error(f'No email found for VM #{vm_data["idVM"]}. Sending to {settings.SEND_TO_FAIL} instead.')
            email = settings.SEND_TO_FAIL
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/scheduled_delete_success.j2').render(
            compute_url=settings.COMPUTE_UI_URL,
            **vm_data,
        )
        # Format the subject
        subject = settings.SUBJECT_VM_SCHEDULE_DELETE
        EmailNotifier._compose_email(email, subject, body)

    # ############################################################## #
    #                     Email Specific Methods                     #
    # ############################################################## #

    @staticmethod
    def _compose_email(email: str, subject: str, body: str):
        """
        Given an email address, subject and body, compile and send email, returning a success flag
        """
        message = MIMEMultipart('alternative')

        # Populate the headers
        message['subject'] = subject
        message['To'] = email
        message['From'] = settings.EMAIL_USERNAME
        message['Reply-To'] = settings.EMAIL_REPLY_TO

        # Attach the body of the email
        message.attach(MIMEText(body, 'html'))

        # Attach the images
        for image in EmailNotifier.message_images:
            path = os.path.join(os.getcwd(), 'templates/emails/assets', image)
            with open(path, 'rb') as f:
                mime_image = MIMEImage(f.read())
            mime_image.add_header('Content-ID', f'<{image}>')
            message.attach(mime_image)

        # Send the email
        EmailNotifier._send(email, message)

    @staticmethod
    def _send(email: str, message: MIMEMultipart):
        """
        Given a receiver's email address and a composed message, attempt to send the message
        """
        logger = logging.getLogger('robot.email_notifier.send_email')
        try:
            server = smtplib.SMTP(settings.EMAIL_HOST, timeout=10)
            # Log in to the server
            server.starttls()
            server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
            server.sendmail(settings.EMAIL_USERNAME, [email], message.as_string())
            server.quit()
            logger.debug(f'Successfully sent notification to {email}')
            return True
        except Exception:
            logger.error(f'Robot failed to send an email to {email}', exc_info=True)
            return False
