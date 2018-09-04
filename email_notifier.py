# python
import logging
import smtplib

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from typing import Optional

# local
import settings
import utils


def vm_email_notifier(subject: str, vm: dict) -> bool:
    """
    This method is dedicated to send mails once a VM is built.
    :param subject: string, context of the mail
    :param vm: dict, vm details
    :return:
    """
    driver_logger = utils.get_logger_for_name(
        'email_notifier.vm_email_notifier',
        logging.DEBUG,
    )

    receiver = vm['user_email_id']
    sender = settings.CLOUDCIX_EMAIL_USERNAME
    sender_password = settings.CLOUDCIX_EMAIL_PASSWORD
    email_smtp = settings.CLOUDCIX_EMAIL_SMTP
    # Create message container with the correct MIME
    # type is multipart/alternative here!
    message = MIMEMultipart('alternative')
    message['subject'] = subject
    message['To'] = receiver
    message['From'] = sender
    message.preamble = 'Your mail reader does not support the report format.'
    # Get the body from template
    body = utils.jinja_env.get_template(
        'vm_email_notifier.j2',
    ).render(subject=subject, **vm)
    # Record the MIME type text/html.
    html_body = MIMEText(body, 'html')
    # Attach parts into message container.
    message.attach(html_body)
    # attach all images or attachments
    with open('templates/assets/CloudCIX_logo.bmp', 'rb') as fp:
        msg_image = MIMEImage(fp.read())
    msg_image.add_header('Content-ID', '<CloudCIX_logo.bmp>')
    message.attach(msg_image)
    with open('templates/assets/twitter.png', 'rb') as fp1:
        msg_image1 = MIMEImage(fp1.read())
    msg_image1.add_header('Content-ID', '<twitter.png>')
    message.attach(msg_image1)
    with open('templates/assets/website.png', 'rb') as fp2:
        msg_image2 = MIMEImage(fp2.read())
    msg_image2.add_header('Content-ID', '<website.png>')
    message.attach(msg_image2)
    # call for sending mail
    sent = send_email(sender, sender_password, receiver, email_smtp, message)
    if sent is True:
        driver_logger.info(
            f'Email is sent successfully to {receiver} '
            f'from {sender} about #VM {vm["vm_identifier"]} status.',
        )
    else:
        driver_logger.error(
            f'Failed to send email to {receiver} from {sender}'
            f' about #VM {vm["vm_identifier"]} status.',
        )
    return sent


def send_email(
        sender: str,
        password: str,
        receiver: str,
        email_smtp: str,
        message: Optional[MIMEMultipart] = None,
)-> bool:
    """
    With this function we send out our html email
    :param sender: string, sender's email id
    :param password: string, sender's password
    :param receiver: string, receiver's email id
    :param email_smtp: string, mail servers like webmail, gmail.
    :param message: Optional, message can html, simple text etc,.
    :return: boolean, True on success and False on failure.
    """
    driver_logger = utils.get_logger_for_name(
        'email_notifier.send_email',
        logging.DEBUG,
    )

    try:
        server = smtplib.SMTP(email_smtp)
        # Credentials for sending the mail (needed)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, [receiver], message.as_string())
        server.quit()
        return True
    except Exception:
        driver_logger.error(
            f'Failed to send mail to {receiver} from {sender}.',
            exc_info=True,
        )
        return False
