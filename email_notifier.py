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
    def vm_failure(vm_data: Dict[str, Any], task: str):
        """
        Report any kind of failure to the NOC and developers emails
        """
        logger = logging.getLogger('robot.email_notifier.failure')
        logger.debug(f'Sending failure email for VM #{vm_data["id"]}')
        # Add the pretty printed data blob to the VM
        vm_data['data'] = dumps(vm_data, indent=2, cls=utils.DequeEncoder)
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/vm_failure.j2').render(
            compute_url=settings.COMPUTE_UI_URL,
            task=task,
            **vm_data,
        )
        # Format the subject
        subject = settings.SUBJECT_PROJECT_FAIL
        EmailNotifier._compose_email(settings.SEND_TO_FAIL, subject, body)

    @staticmethod
    def virtual_router_failure(virtual_router_data: Dict[str, Any], task: str):
        """
        Report any kind of failure to the NOC and developers emails
        """
        logger = logging.getLogger('robot.email_notifier.virtual_router_failure')
        logger.debug(f'Sending failure email for virtual_router #{virtual_router_data["id"]}')
        # Add the pretty printed data blob to the virtual_router
        virtual_router_data['data'] = dumps(virtual_router_data, indent=2, cls=utils.DequeEncoder)
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/virtual_router_failure.j2').render(
            compute_url=settings.COMPUTE_UI_URL,
            task=task,
            **virtual_router_data,
        )
        # Format the subject
        subject = settings.SUBJECT_VIRTUAL_ROUTER_FAIL
        EmailNotifier._compose_email(settings.SEND_TO_FAIL, subject, body)

    # ############################################################## #
    #                              BUILD                             #
    # ############################################################## #

    @staticmethod
    def vm_build_success(vm_data: Dict[str, Any]):
        """
        Given a VM's details, render and send a build success email
        """
        logger = logging.getLogger('robot.email_notifier.build_success')
        logger.debug(f'Sending build success email for VM #{vm_data["id"]}')
        # Check that the data contains an email
        email = vm_data.get('email', None)
        if email is None:
            logger.error(f'No email found for VM #{vm_data["id"]}. Sending to {settings.SEND_TO_FAIL} instead.')
            email = settings.SEND_TO_FAIL
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/vm_build_success.j2').render(
            compute_url=settings.COMPUTE_UI_URL,
            **vm_data,
        )
        # Format the subject
        subject = settings.SUBJECT_VM_SUCCESS
        EmailNotifier._compose_email(email, subject, body)

    @staticmethod
    def vpn_build_success(vpn_data: Dict[str, Any]):
        """
        Given a VPN's details, render and send a build success email
        """
        vpn_id = vpn_data['id']
        logger = logging.getLogger('robot.email_notifier.vpn_build_success')
        logger.debug(f'Sending build success email for VPN #{vpn_id}')
        # Check that the data contains an email
        emails = vpn_data.get('emails', None)
        if emails is None:
            logger.error(f'No email found for VPN #{vpn_id}. Sending to {settings.SEND_TO_FAIL} instead.')
            emails = [settings.SEND_TO_FAIL]
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/vpn_success.j2').render(
            compute_url=settings.COMPUTE_UI_URL,
            build=True,
            **vpn_data,
        )
        # Format the subject
        subject = settings.SUBJECT_VPN_BUILD_SUCCESS
        for email in emails:
            EmailNotifier._compose_email(email, subject, body)

    @staticmethod
    def vpn_update_success(vpn_data: Dict[str, Any]):
        """
        Given a VPN's details, render and send a update success email
        """
        vpn_id = vpn_data['id']
        logger = logging.getLogger('robot.email_notifier.vpn_update_success')
        logger.debug(f'Sending update success email for VPN #{vpn_id}')
        # Check that the data contains an email
        emails = vpn_data.get('emails', None)
        if emails is None:
            logger.error(f'No email found for VPN #{vpn_id}. Sending to {settings.SEND_TO_FAIL} instead.')
            emails = [settings.SEND_TO_FAIL]
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/vpn_success.j2').render(
            compute_url=settings.COMPUTE_UI_URL,
            build=False,
            **vpn_data,
        )
        # Format the subject
        subject = settings.SUBJECT_VPN_UPDATE_SUCCESS
        for email in emails:
            EmailNotifier._compose_email(email, subject, body)

    @staticmethod
    def vm_build_failure(vm_data: Dict[str, Any]):
        """
        Given a VM's details, render and send a build failure email
        """
        logger = logging.getLogger('robot.email_notifier.build_failure')
        logger.debug(f'Sending build failure email for VM #{vm_data["id"]}')
        # Check that the data contains an email
        email = vm_data.get('email', None)
        if email is None:
            logger.error(f'No email found for VM #{vm_data["id"]}. Sending to {settings.SEND_TO_FAIL} instead.')
            email = settings.SEND_TO_FAIL
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/vm_build_failure.j2').render(
            compute_url=settings.COMPUTE_UI_URL,
            **vm_data,
        )
        # Format the subject
        subject = settings.SUBJECT_VM_FAIL
        EmailNotifier._compose_email(email, subject, body)

        # Also run the generic failure method to pass failures to us
        EmailNotifier.vm_failure(vm_data, 'build')

    # ############################################################## #
    #                             QUIESCE                            #
    # ############################################################## #

    @staticmethod
    def delete_schedule_success(vm_data: Dict[str, Any]):
        """
        Given a VM's details, render and send a delete_schedule success email
        """
        logger = logging.getLogger('robot.email_notifier.delete_schedule_success')
        logger.debug(f'Sending delete scheduled email for VM #{vm_data["id"]}')
        # Check that the data contains an email
        email = vm_data.get('email', None)
        if email is None:
            logger.error(f'No email found for VM #{vm_data["id"]}. Sending to {settings.SEND_TO_FAIL} instead.')
            email = settings.SEND_TO_FAIL
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/scheduled_delete_success.j2').render(
            compute_url=settings.COMPUTE_URL,
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
