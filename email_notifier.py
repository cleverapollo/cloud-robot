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

STAGE = settings.REGION_NAME == 'alpha'


class EmailNotifier:
    # A list of image files that need to be attached to the emails
    message_images = ['cloudcix_logo.bmp', 'twitter.png', 'website.png']

    # ############################################################## #
    #                               NOC                              #
    # ############################################################## #

    @staticmethod
    def failure(vm_data: Dict[str, Any]):
        """
        Report any kind of failure to the NOC and developers emails
        """
        logger = logging.getLogger('robot.email_notifier.failure')
        logger.debug(f'Sending failure email for VM #{vm_data["idVM"]}')
        # Add the pretty printed data blob to the VM
        vm_data['data'] = dumps(vm_data, indent=2)
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/failure.j2').render(stage=STAGE, **vm_data)
        # Format the subject
        subject = f'[CloudCIX] VM Failure Occurred!'
        EmailNotifier._compose_email('developers@cloudcix.com', subject, body)

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
        name = vm_data['name']
        # Check that the data contains an email
        email = vm_data.get('email', None)
        if email is None:
            logger.error(f'No email found for VM #{vm_data["idVM"]}. Sending to developers@cloudcix.com instead.')
            email = 'developers@cloudcix.com'
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/build_success.j2').render(stage=STAGE, **vm_data)
        # Format the subject
        subject = f'[CloudCIX] Your VM "{name}" has been built successfully!'
        EmailNotifier._compose_email(email, subject, body)

    @staticmethod
    def build_failure(vm_data: Dict[str, Any]):
        """
        Given a VM's details, render and send a build failure email
        """
        logger = logging.getLogger('robot.email_notifier.build_failure')
        logger.debug(f'Sending build failure email for VM #{vm_data["idVM"]}')
        name = vm_data['name']
        # Check that the data contains an email
        email = vm_data.get('email', None)
        if email is None:
            logger.error(f'No email found for VM #{vm_data["idVM"]}. Sending to developers@cloudcix.com instead.')
            email = 'developers@cloudcix.com'
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/build_failure.j2').render(stage=STAGE, **vm_data)
        # Format the subject
        subject = f'[CloudCIX] Your VM "{name}" has failed to build.'
        EmailNotifier._compose_email(email, subject, body)

        # Also run the generic failure method to pass failures to us
        EmailNotifier.failure(vm_data)

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
        name = vm_data['name']
        # Check that the data contains an email
        email = vm_data.get('email', None)
        if email is None:
            logger.error(f'No email found for VM #{vm_data["idVM"]}. Sending to developers@cloudcix.com instead.')
            email = 'developers@cloudcix.com'
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/scheduled_delete_success.j2').render(stage=STAGE, **vm_data)
        # Format the subject
        subject = f'[CloudCIX] Your VM "{name}" has been scheduled for deletion!'
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
        message['From'] = settings.CLOUDCIX_EMAIL_USERNAME
        message['Reply-To'] = 'CloudCIX <no-reply@cloudcix.net>'
        message.preamble = 'Your mail reader does not support the report format. This is an HTML email.'

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
            server = smtplib.SMTP('mail.cloudcix.net', timeout=10)
            # Log in to the server
            server.starttls()
            server.login('notification@cloudcix.net', 'C1xacc355')
            server.sendmail(settings.CLOUDCIX_EMAIL_USERNAME, [email], message.as_string())
            server.quit()
            logger.debug(f'Successfully sent notification to {email}')
            return True
        except Exception:
            logger.error(f'Robot failed to send an email to {email}', exc_info=True)
            return False
