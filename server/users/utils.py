import random
from django.core.mail import EmailMessage
from .models import User
from django.conf import settings


"""
def generateOtp():

    otp = ''
    for i in range(6):
        otp += str(random.randint(1, 9))
    return otp

def send_code_to_user(email):

    Subject = 'One time passcode for email verification'
    otp_code = generateOtp()
    print(otp_code)
    user = User.objects.get(email=email)
    current_site = 'myauth.com'
    email_body = f'Hi {user.first_name},thanks for for signing up on {current_site} please verify your email \n with the one time passcode {otp_code} via link http://localhost:8000/api/users/verify-email/'
    from_email = settings.DEFAULT_FROM_EMAIL

    OneTimePassword.objects.create(user=user, code=otp_code)

    d_email = EmailMessage(subject=Subject, body=email_body, from_email=from_email, to=[email])
    d_email.send(fail_silently=True)
"""

def send_normal_email(data):
    """
    Send email using Mailgun API (bypasses Django's email backend and SMTP issues).
    """
    import logging
    import requests
    import os
    
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Attempting to send email to {data['to_email']} via Mailgun API")
        
        # Get Mailgun credentials from environment
        api_key = os.getenv('MAILGUN_API_KEY')
        domain = os.getenv('MAILGUN_DOMAIN')
        
        if not api_key or not domain:
            raise Exception("MAILGUN_API_KEY or MAILGUN_DOMAIN not set in .env")
        
        # Mailgun API endpoint (US region)
        url = f"https://api.mailgun.net/v3/{domain}/messages"
        
        logger.info(f"Mailgun URL: {url}")
        logger.info(f"Using API key: {api_key[:20]}...")
        
        # Send email via Mailgun API
        response = requests.post(
            url,
            auth=("api", api_key),
            data={
                "from": f"Kifaru Impact <postmaster@{domain}>",
                "to": [data['to_email']],
                "subject": data['email_subject'],
                "text": data['email_body']
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Email sent successfully via Mailgun API. ID: {result.get('id')}")
        else:
            logger.error(f"Mailgun API error: {response.status_code} - {response.text}")
            raise Exception(f"Mailgun failed: {response.text}")
        
    except Exception as e:
        logger.error(f"Email sending failed: {type(e).__name__}: {str(e)}")
        logger.error(f"Full error details:", exc_info=True)
        raise
        
        response = requests.post(
            url,
            auth=("api", api_key),
            data={
                "from": from_email,
                "to": [data['to_email']],
                "subject": data['email_subject'],
                "text": data['email_body']
            }
        )
        
        if response.status_code == 200:
            logger.info(f"Email sent successfully via Mailgun. ID: {response.json().get('id')}")
        else:
            logger.error(f"Mailgun API error: {response.status_code} - {response.text}")
            raise Exception(f"Mailgun failed: {response.text}")
        
    except Exception as e:
        logger.error(f"Email sending failed: {type(e).__name__}: {str(e)}")
        logger.error(f"Full error details:", exc_info=True)
        raise

