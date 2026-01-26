from rest_framework import serializers
from .models import User
from django.contrib.auth import authenticate
from rest_framework.exceptions import AuthenticationFailed
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import smart_str, smart_bytes, force_str
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.contrib.sites.shortcuts import get_current_site
from django.urls import reverse
from .utils import send_normal_email
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from django.conf import settings
import phonenumbers
from phonenumbers import geocoder


class UserRegisterSerializer(serializers.ModelSerializer):

    password = serializers.CharField(max_length=68, min_length=6, write_only=True)
    password_confirm = serializers.CharField(max_length=68, min_length=6, write_only=True)

    class Meta:

        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'phone_number', 'whatsapp_number',
            'preferred_language', 'country_of_residence', 'password', 'password_confirm'
        ]
    
    def validate_phone_number(self, value):
        """Validate phone number format - must include country code"""
        if not value:
            return value
            
        if not value.startswith('+'):
            raise serializers.ValidationError(
                "Phone number must include country code (e.g., +254712345678, +32475123456)"
            )
        
        try:
            parsed = phonenumbers.parse(value, None)
            if not phonenumbers.is_valid_number(parsed):
                raise serializers.ValidationError("Invalid phone number")
        except phonenumbers.NumberParseException:
            raise serializers.ValidationError(
                "Invalid phone number format. Use international format: +[country code][number]"
            )
        
        return value
    
    def validate_whatsapp_number(self, value):
        """Validate WhatsApp number format - must include country code"""
        if not value:
            return value
            
        if not value.startswith('+'):
            raise serializers.ValidationError(
                "WhatsApp number must include country code (e.g., +254712345678, +32475123456)"
            )
        
        try:
            parsed = phonenumbers.parse(value, None)
            if not phonenumbers.is_valid_number(parsed):
                raise serializers.ValidationError("Invalid WhatsApp number")
        except phonenumbers.NumberParseException:
            raise serializers.ValidationError(
                "Invalid WhatsApp number format. Use international format: +[country code][number]"
            )
        
        return value

    def validate(self, attr):

        password = attr.get('password', '')
        password_confirm = attr.get('password_confirm', '')
        if password != password_confirm:
            raise serializers.ValidationError('passwords do not match')
        
        # Auto-detect country from phone number if not provided
        phone_number = attr.get('phone_number', '')
        country_of_residence = attr.get('country_of_residence', '')
        
        if phone_number and not country_of_residence:
            try:
                parsed = phonenumbers.parse(phone_number, None)
                country = geocoder.description_for_number(parsed, "en")
                if country:
                    attr['country_of_residence'] = country
            except:
                pass  # If parsing fails, leave country empty
        
        return attr

    def create(self, validated_data):
        
        user = User.objects.create_user(
            email = validated_data['email'],
            first_name = validated_data['first_name'],
            last_name = validated_data['last_name'],
            phone_number = validated_data.get('phone_number', ''),
            whatsapp_number = validated_data.get('whatsapp_number', ''),
            preferred_language = validated_data.get('preferred_language', 'english'),
            country_of_residence = validated_data.get('country_of_residence', ''),
            password = validated_data['password'],
            is_verified = True
        )
        return user
    
class LoginSerializer(serializers.Serializer):
    id            = serializers.IntegerField(read_only=True)
    first_name    = serializers.CharField(read_only=True)  # Fixed typo: was 'fist_name'
    last_name     = serializers.CharField(read_only=True)
    role          = serializers.CharField(read_only=True)
    access_token  = serializers.CharField(read_only=True)
    refresh_token = serializers.CharField(read_only=True)
    email    = serializers.EmailField(max_length=255)
    password = serializers.CharField(write_only=True, max_length=128)

    def validate(self, attrs):
        email    = attrs.get('email')
        password = attrs.get('password')
        user = authenticate(
            request=self.context.get('request'),
            email=email,
            password=password
        )

        if not user:
            raise AuthenticationFailed("Invalid credentials, try again.")
        # if not user.is_verified:
        #     raise AuthenticationFailed("Email is not verified.")

        # Generate JWT tokens
        tokens = user.tokens()

        return {
            'id':            user.pk,
            'first_name':     user.first_name,
            'last_name':     user.last_name,
            'email':         user.email,
            'phone_number':  user.phone_number,
            'whatsapp_number': user.whatsapp_number,
            'preferred_language': user.preferred_language,
            'country_of_residence': user.country_of_residence,
            'is_returning_guest': user.is_returning_guest,
            'role':          user.role,
            'access_token':  tokens['access'],
            'refresh_token': tokens['refresh'],
        }

    def to_representation(self, validated_data):
        return validated_data

class LogoutSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()

    def validate(self, attrs):
        self.token = attrs['refresh_token']
        return attrs

    def save(self, **kwargs):
        try:
            RefreshToken(self.token).blacklist()
        except TokenError:
            raise serializers.ValidationError('Invalid or expired token')

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=255)

    class Meta:
        fields = ['email']

    def validate(self, attrs):
        email = attrs.get('email') 
        if User.objects.filter(email=email).exists():
            user = User.objects.get(email=email)
            uidb64 = urlsafe_base64_encode(smart_bytes(user.id))
            token = PasswordResetTokenGenerator().make_token(user)
            
            # Get frontend URL from settings
            frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
            
            # Build the frontend reset link (matches React route /password-reset/:uidb64/:token)
            reset_link = f"{frontend_url}/password-reset/{uidb64}/{token}/"
            
            email_body = f'Hi {user.first_name},\n\nUse the link below to reset your password:\n\n{reset_link}\n\nIf you did not request a password reset, please ignore this email.'
            
            data = {
                'email_body': email_body,
                'email_subject': 'Reset your password',
                'to_email': user.email
            }
            try:
                send_normal_email(data)
            except Exception as e:
                # Log the error but don't fail the request
                # This prevents exposing whether an email exists in the system
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to send password reset email: {str(e)}")
        return super().validate(attrs)   


class SetNewPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=100, min_length=6, write_only=True)
    password_confirm = serializers.CharField(max_length=100, min_length=6, write_only=True)
    uidb64 = serializers.CharField(write_only=True)
    token = serializers.CharField(write_only=True)

    class Meta:
        fields = ['password', 'password_confirm', 'uidb64', 'token']

    def validate(self, attrs):
        try:
            password = attrs.get('password')
            password_confirm = attrs.get('password_confirm')
            uidb64 = attrs.get('uidb64')
            token = attrs.get('token')

            user_id = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(id=user_id)

            if not PasswordResetTokenGenerator().check_token(user, token):
                raise AuthenticationFailed('reset link is invalid or has expired', 401)
            if password != password_confirm:
                raise AuthenticationFailed('password does not match')
        
            user.set_password(password)
            user.save()
            return user
        except Exception as e:
            raise AuthenticationFailed('link is invalid or has expired')  # Fixed: was return, should be raise

class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile - returns complete user information"""
    assigned_properties = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'phone_number', 'whatsapp_number',
            'preferred_language', 'country_of_residence', 'is_returning_guest', 'special_preferences',
            'role', 'is_active', 'is_verified', 'assigned_properties',
            'date_joined', 'last_login'
        ]
        read_only_fields = ['id', 'email', 'date_joined', 'last_login', 'is_returning_guest', 'role', 'is_active', 'is_verified']
    
    def validate_phone_number(self, value):
        """Validate phone number format - must include country code"""
        if not value:
            return value
            
        if not value.startswith('+'):
            raise serializers.ValidationError(
                "Phone number must include country code (e.g., +254712345678, +32475123456)"
            )
        
        try:
            parsed = phonenumbers.parse(value, None)
            if not phonenumbers.is_valid_number(parsed):
                raise serializers.ValidationError("Invalid phone number")
        except phonenumbers.NumberParseException:
            raise serializers.ValidationError(
                "Invalid phone number format. Use international format: +[country code][number]"
            )
        
        return value
    
    def validate_whatsapp_number(self, value):
        """Validate WhatsApp number format - must include country code"""
        if not value:
            return value
            
        if not value.startswith('+'):
            raise serializers.ValidationError(
                "WhatsApp number must include country code (e.g., +254712345678, +32475123456)"
            )
        
        try:
            parsed = phonenumbers.parse(value, None)
            if not phonenumbers.is_valid_number(parsed):
                raise serializers.ValidationError("Invalid WhatsApp number")
        except phonenumbers.NumberParseException:
            raise serializers.ValidationError(
                "Invalid WhatsApp number format. Use international format: +[country code][number]"
            )
        
        return value
    
    def validate(self, attrs):
        """Auto-detect country from phone number if not provided"""
        phone_number = attrs.get('phone_number')
        country_of_residence = attrs.get('country_of_residence')
        
        # Only auto-detect if phone is being updated and country is empty
        if phone_number and not country_of_residence:
            # Check if user already has country set
            if self.instance and self.instance.country_of_residence:
                # Keep existing country
                attrs['country_of_residence'] = self.instance.country_of_residence
            else:
                # Auto-detect from phone number
                try:
                    parsed = phonenumbers.parse(phone_number, None)
                    country = geocoder.description_for_number(parsed, "en")
                    if country:
                        attrs['country_of_residence'] = country
                except:
                    pass  # If parsing fails, leave country empty
        
        return attrs
    
    def get_assigned_properties(self, obj):
        """Return assigned properties for staff users"""
        if obj.role == 'staff':
            return [
                {
                    'id': prop.id,
                    'name': prop.name,
                    'slug': prop.slug,
                    'location': prop.location
                }
                for prop in obj.assigned_properties.all()
            ]
        return []

class UserListSerializer(serializers.ModelSerializer):
    """serializer for admin user management"""

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'phone_number', 'whatsapp_number',
            'preferred_language', 'country_of_residence', 'is_returning_guest', 'special_preferences',
            'role', 'is_active', 'is_verified', 'is_staff',
            'date_joined', 'last_login'
        ]
        read_only_fields = ['date_joined', 'last_login', 'is_returning_guest']

class UserStatsSerializer(serializers.Serializer):
    total_users = serializers.IntegerField()
    active_users = serializers.IntegerField()
    verified_users = serializers.IntegerField()
    users_by_role = serializers.DictField(child=serializers.IntegerField())