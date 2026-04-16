"""
Paystack payment utilities for kifaru2 booking platform
"""
from django.conf import settings
from paystackapi.paystack import Paystack
from paystackapi.transaction import Transaction
import logging

logger = logging.getLogger(__name__)

# Initialize Paystack with secret key
paystack = Paystack(secret_key=settings.PAYSTACK_SECRET_KEY)


def initialize_payment(email, amount, reference, callback_url=None, metadata=None):
    """
    Initialize a Paystack payment transaction
    
    Args:
        email (str): Customer email address
        amount (Decimal): Amount in the smallest currency unit (kobo for NGN, cents for USD/KES)
        reference (str): Unique transaction reference
        callback_url (str, optional): URL to redirect after payment
        metadata (dict, optional): Additional data (booking_id, user_id, etc.)
    
    Returns:
        dict: {
            'status': bool,
            'data': {
                'authorization_url': str,
                'access_code': str,
                'reference': str
            },
            'message': str
        }
    """
    try:
        # Convert amount to kobo/cents (Paystack requires integer)
        amount_in_kobo = int(float(amount) * 100)
        
        # Prepare transaction data
        transaction_data = {
            'email': email,
            'amount': amount_in_kobo,
            'reference': reference,
        }
        
        if callback_url:
            transaction_data['callback_url'] = callback_url
        
        if metadata:
            transaction_data['metadata'] = metadata
        
        # Initialize transaction
        response = Transaction.initialize(**transaction_data)
        
        logger.info(f"Paystack payment initialized: {reference}")
        return {
            'status': True,
            'data': response['data'],
            'message': 'Payment initialized successfully'
        }
        
    except Exception as e:
        logger.error(f"Paystack initialization error for {reference}: {str(e)}")
        return {
            'status': False,
            'data': None,
            'message': f'Payment initialization failed: {str(e)}'
        }


def verify_payment(reference):
    """
    Verify a Paystack payment transaction
    
    Args:
        reference (str): Transaction reference to verify
    
    Returns:
        dict: {
            'status': bool,
            'data': {
                'status': str,  # 'success', 'failed', 'abandoned'
                'amount': int,  # Amount in kobo/cents
                'paid_at': str,
                'reference': str,
                'customer': dict,
                'metadata': dict
            },
            'message': str
        }
    """
    try:
        response = Transaction.verify(reference=reference)
        
        if response['status']:
            logger.info(f"Payment verified successfully: {reference}")
            return {
                'status': True,
                'data': response['data'],
                'message': 'Payment verified successfully'
            }
        else:
            logger.warning(f"Payment verification failed: {reference}")
            return {
                'status': False,
                'data': response.get('data'),
                'message': response.get('message', 'Verification failed')
            }
            
    except Exception as e:
        logger.error(f"Paystack verification error for {reference}: {str(e)}")
        return {
            'status': False,
            'data': None,
            'message': f'Payment verification failed: {str(e)}'
        }


def verify_webhook_signature(request_body, signature):
    """
    Verify that a webhook request actually came from Paystack
    
    Args:
        request_body (bytes): Raw request body
        signature (str): X-Paystack-Signature header value
    
    Returns:
        bool: True if signature is valid
    """
    import hmac
    import hashlib
    
    try:
        secret_key = settings.PAYSTACK_SECRET_KEY.encode('utf-8')
        computed_signature = hmac.new(
            secret_key,
            msg=request_body,
            digestmod=hashlib.sha512
        ).hexdigest()
        
        return hmac.compare_digest(computed_signature, signature)
        
    except Exception as e:
        logger.error(f"Webhook signature verification error: {str(e)}")
        return False


def get_transaction_status(reference):
    """
    Get the current status of a transaction
    
    Args:
        reference (str): Transaction reference
    
    Returns:
        str: 'success', 'failed', 'pending', 'abandoned', or 'unknown'
    """
    try:
        result = verify_payment(reference)
        if result['status'] and result['data']:
            return result['data'].get('status', 'unknown')
        return 'unknown'
    except Exception as e:
        logger.error(f"Error fetching transaction status: {str(e)}")
        return 'unknown'
