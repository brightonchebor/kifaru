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
    Send email using Resend API (production) or SMTP (development).
    Resend is used in production to avoid SMTP port blocking issues.
    """
    import logging
    import os
    
    logger = logging.getLogger(__name__)
    
    # Check if Resend API key is available (production)
    resend_api_key = os.getenv('RESEND_API_KEY')
    
    if resend_api_key:
        # Use Resend API (production - no SMTP blocking issues)
        try:
            import resend
            
            logger.info(f"Attempting to send email to {data['to_email']} via Resend API")
            
            resend.api_key = resend_api_key
            
            params = {
                "from": settings.DEFAULT_FROM_EMAIL,
                "to": [data['to_email']],
                "subject": data['email_subject'],
                "text": data['email_body']
            }
            
            email = resend.Emails.send(params)
            logger.info(f"Email sent successfully via Resend API to {data['to_email']}")
            
        except Exception as e:
            logger.error(f"Resend API failed: {type(e).__name__}: {str(e)}")
            logger.error(f"Full error details:", exc_info=True)
            # Don't raise - just log the error
    else:
        # Fallback to SMTP (development/local)
        from concurrent.futures import ThreadPoolExecutor, TimeoutError
        
        def _send_email_task():
            """Internal function to send email via SMTP"""
            try:
                logger.info(f"Attempting to send email to {data['to_email']} via SMTP")
                
                email = EmailMessage(
                    subject=data['email_subject'],
                    body=data['email_body'],
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[data['to_email']]
                )
                
                email.send(fail_silently=False)
                logger.info(f"Email sent successfully to {data['to_email']}")
                return True
                
            except Exception as e:
                logger.error(f"SMTP email sending failed: {type(e).__name__}: {str(e)}")
                raise
        
        # Execute email sending with timeout
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_send_email_task)
                future.result(timeout=15)
        except TimeoutError:
            logger.warning(f"SMTP email timed out after 15 seconds to {data['to_email']}")
        except Exception as e:
            logger.error(f"Email sending failed: {str(e)}")

