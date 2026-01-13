from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from rest_framework_simplejwt.tokens import RefreshToken
from .managers import UserManager
from django.utils.translation import gettext_lazy as _

class User(AbstractBaseUser, PermissionsMixin):

    """
    Custom user model extending Django's AbstractUser.
    Adds role-based access control and additional user information.
    Username, email and password are required
    """
    
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('staff', 'Staff'),
        ('concierge', 'Concierge'),
        ('property_manager', 'Property Manager'),
        ('external', 'External Client'),
    ]
    
    LANGUAGE_CHOICES = [
        ('english', 'English'),
        ('french', 'French'),
        ('dutch', 'Dutch'),
        ('swahili', 'Swahili'),
    ]
    
    email = models.EmailField(max_length=255, unique=True, verbose_name=_("Email Address"))
    first_name = models.CharField(max_length=100, verbose_name=_("First Name"))
    last_name = models.CharField(max_length=100, verbose_name=_("Last Name"))
    phone_number = models.CharField(max_length=20, blank=True, verbose_name=_("Phone Number"))
    whatsapp_number = models.CharField(max_length=20, blank=True, verbose_name=_("WhatsApp Number"))
    
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(auto_now=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='external', db_index=True)
    
    # Additional guest information
    preferred_language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, default='english')
    country_of_residence = models.CharField(max_length=100, blank=True)
    is_returning_guest = models.BooleanField(default=False)
    special_preferences = models.JSONField(default=dict, blank=True, help_text="Dietary, room preferences, etc.")
    
    # Staff property assignments
    assigned_properties = models.ManyToManyField(
        'properties.Property',
        blank=True,
        related_name='assigned_staff',
        help_text="Properties this staff member is assigned to manage"
    )
   

    USERNAME_FIELD = "email"

    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    def __str__(self):
        return self.email

    @property
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    def tokens(self):
        refresh = RefreshToken.for_user(self)

        return {
            'refresh':str(refresh),
            'access':str(refresh.access_token)
        }


