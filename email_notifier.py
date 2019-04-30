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
from typing import Any, Dict
# local
import settings
import utils

__all__ = [
    'EmailNotifier',
]


class EmailNotifier:
    # A list of image files that need to be attached to the emails
    message_images = ['cloudcix_logo.bmp', 'twitter.png', 'website.png']

    # Build Email Subject Templates
    build_success_subject = 'Your VM "{name}" has been built successfully!'
    build_failure_subject = 'Your VM "{name}" has failed to build.'

    # Quiesce Email Subject Templates
    quiesce_success_subject = 'Your VM "{name}" has been shut down successfully!'

    # Restart Email Subject Templates
    restart_success_subject = 'Your VM "{name}" has been restarted successfully!'
    restart_failure_subject = 'Your VM "{name}" failed to restart'

    # Update Email Subject Templates
    update_success_subject = 'Your VM "{name}" has been updated successfully!'
    update_failure_subject = 'Your VM "{name}" failed to update'

    # ############################################################## #
    #                              BUILD                             #
    # ############################################################## #

    @staticmethod
    def build_success(vm_data: Dict[str, Any]):
        """
        Given a VM's details, render and send a build success email
        """
        logger = logging.getLogger('email_notifier.build_success')
        # Check that the data contains an email
        email = vm_data.pop('email', None)
        if email is None:
            logger.error(f'No email found for VM #{vm_data["idVM"]}. Sending to developers@cloudcix.com instead.')
            email = 'developers@cloudcix.com'
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/build_success.j2').render(**vm_data)
        # Format the subject
        subject = f'[CloudCIX] {EmailNotifier.build_success_subject.format(vm_data["name"])}'
        EmailNotifier._compose_email(email, subject, body)

    @staticmethod
    def build_failure(vm_data: Dict[str, Any]):
        """
        Given a VM's details, render and send a build failure email
        """
        logger = logging.getLogger('email_notifier.build_failure')
        # Check that the data contains an email
        email = vm_data.pop('email', None)
        if email is None:
            logger.error(f'No email found for VM #{vm_data["idVM"]}. Sending to developers@cloudcix.com instead.')
            email = 'developers@cloudcix.com'
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/build_failure.j2').render(**vm_data)
        # Format the subject
        subject = f'[CloudCIX] {EmailNotifier.build_failure_subject.format(vm_data["name"])}'
        EmailNotifier._compose_email(email, subject, body)

    # ############################################################## #
    #                             QUIESCE                            #
    # ############################################################## #

    @staticmethod
    def quiesce_success(vm_data: Dict[str, Any]):
        """
        Given a VM's details, render and send a quiesce success email
        """
        logger = logging.getLogger('email_notifier.quiesce_success')
        # Check that the data contains an email
        email = vm_data.pop('email', None)
        if email is None:
            logger.error(f'No email found for VM #{vm_data["idVM"]}. Sending to developers@cloudcix.com instead.')
            email = 'developers@cloudcix.com'
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/quiesce_success.j2').render(**vm_data)
        # Format the subject
        subject = f'[CloudCIX] {EmailNotifier.quiesce_success_subject.format(vm_data["name"])}'
        EmailNotifier._compose_email(email, subject, body)

    @staticmethod
    def delete_schedule_success(vm_data: Dict[str, Any]):
        """
        Given a VM's details, render and send a delete_schedule success email
        """
        logger = logging.getLogger('email_notifier.delete_schedule_success')
        # Check that the data contains an email
        email = vm_data.pop('email', None)
        if email is None:
            logger.error(f'No email found for VM #{vm_data["idVM"]}. Sending to developers@cloudcix.com instead.')
            email = 'developers@cloudcix.com'
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/scheduled_delete_success.j2').render(**vm_data)
        # Format the subject
        subject = f'[CloudCIX] {EmailNotifier.quiesce_success_subject.format(vm_data["name"])}'
        EmailNotifier._compose_email(email, subject, body)

    # ############################################################## #
    #                             RESTART                            #
    # ############################################################## #

    @staticmethod
    def restart_success(vm_data: Dict[str, Any]):
        """
        Given a VM's details, render and send a restart success email
        """
        logger = logging.getLogger('email_notifier.restart_success')
        # Check that the data contains an email
        email = vm_data.pop('email', None)
        if email is None:
            logger.error(f'No email found for VM #{vm_data["idVM"]}. Sending to developers@cloudcix.com instead.')
            email = 'developers@cloudcix.com'
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/restart_success.j2').render(**vm_data)
        # Format the subject
        subject = f'[CloudCIX] {EmailNotifier.restart_success_subject.format(vm_data["name"])}'
        EmailNotifier._compose_email(email, subject, body)

    @staticmethod
    def restart_failure(vm_data: Dict[str, Any]):
        """
        Given a VM's details, render and send a restart failure email
        """
        logger = logging.getLogger('email_notifier.restart_failure')
        # Check that the data contains an email
        email = vm_data.pop('email', None)
        if email is None:
            logger.error(f'No email found for VM #{vm_data["idVM"]}. Sending to developers@cloudcix.com instead.')
            email = 'developers@cloudcix.com'
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/restart_failure.j2').render(**vm_data)
        # Format the subject
        subject = f'[CloudCIX] {EmailNotifier.restart_failure_subject.format(vm_data["name"])}'
        EmailNotifier._compose_email(email, subject, body)

    # ############################################################## #
    #                             UPDATE                             #
    # ############################################################## #

    @staticmethod
    def update_success(vm_data: Dict[str, Any]):
        """
        Given a VM's details, render and send a update success email
        """
        logger = logging.getLogger('email_notifier.update_success')
        # Check that the data contains an email
        email = vm_data.pop('email', None)
        if email is None:
            logger.error(f'No email found for VM #{vm_data["idVM"]}. Sending to developers@cloudcix.com instead.')
            email = 'developers@cloudcix.com'
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/update_success.j2').render(**vm_data)
        # Format the subject
        subject = f'[CloudCIX] {EmailNotifier.update_success_subject.format(vm_data["name"])}'
        EmailNotifier._compose_email(email, subject, body)

    @staticmethod
    def update_failure(vm_data: Dict[str, Any]):
        """
        Given a VM's details, render and send a update failure email
        """
        logger = logging.getLogger('email_notifier.update_failure')
        # Check that the data contains an email
        email = vm_data.pop('email', None)
        if email is None:
            logger.error(f'No email found for VM #{vm_data["idVM"]}. Sending to developers@cloudcix.com instead.')
            email = 'developers@cloudcix.com'
        # Render the email body
        body = utils.JINJA_ENV.get_template('emails/update_failure.j2').render(**vm_data)
        # Format the subject
        subject = f'[CloudCIX] {EmailNotifier.update_failure_subject.format(vm_data["name"])}'
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
        logger = logging.getLogger('email_notifier.send_email')
        try:
            server = smtplib.SMTP(settings.CLOUDCIX_EMAIL_HOST)
            # Log in to the server
            server.starttls()
            server.login(settings.CLOUDCIX_EMAIL_USERNAME, settings.CLOUDCIX_EMAIL_PASSWORD)
            server.sendmail(settings.CLOUDCIX_EMAIL_USERNAME, [email], message.as_string())
            server.quit()
            logger.debug(f'Successfully sent notification to {email}')
            return True
        except Exception:
            logger.error(f'Robot failed to send an email to {email}', exc_info=True)
            return False
