from pathlib import Path
import os
from datetime import timedelta
import environ
import cloudinary
import cloudinary.uploader
import cloudinary.api

env = environ.Env(
    # Set casting, default value
    DEBUG = (bool, False)
)

BASE_DIR = Path(__file__).resolve().parent.parent

environ.Env.read_env(BASE_DIR / '.env')



SECRET_KEY = "django-insecure-xyid0fm_gm8mddcap09umj4p=7vg)@j)o*1!)rnft^zi!ke^-m"

DEBUG = True

ALLOWED_HOSTS = [
    'localhost',
    'kifaru2-production.up.railway.app',
    # 'http://kifaru2-production.up.railway.app',
    # 'https://kifaru2-production.up.railway.app',
    '127.0.0.1',
    'http://localhost:5173',
    'https://kifaru-git-frontend-asgards-projects.vercel.app',
    'https://kifaru-rust.vercel.app'
]

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    'https://kifaru2-production.up.railway.app',
    'https://kifaru-git-frontend-asgards-projects.vercel.app',
    'https://kifaru-rust.vercel.app'
]       

# CORS Settings - PRODUCTION SAFE
CORS_ALLOW_ALL_ORIGINS = True

CORS_ALLOW_CREDENTIALS = True

# Additional CORS settings for maximum compatibility
CORS_ALLOWED_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'access-control-allow-origin',
]

CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

INSTALLED_APPS = [
    'jazzmin',
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    'drf_yasg',
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'whitenoise.runserver_nostatic',
    'cloudinary_storage',  
    'cloudinary',  
    
    'users',
    'properties',
    'payment',
    'booking',
    'content',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"


# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.sqlite3",
#         "NAME": BASE_DIR / "db.sqlite3",
#     }
# }


DATABASES = {
    'default': {
           
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('PG_NAME'),
        'USER': 'postgres',
        'PASSWORD': env('PG_PWD'),
        'HOST': 'crossover.proxy.rlwy.net',
        'PORT': '17850'
 
    }
}




AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

TIME_ZONE  = "Africa/Nairobi"

STATIC_URL = 'static/'

STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Cloudinary Configuration
cloudinary.config(
    cloud_name=env('CLOUDINARY_CLOUD_NAME'),
    api_key=env('CLOUDINARY_API_KEY'),
    api_secret=env('CLOUDINARY_API_SECRET'),
    secure=True
)

CLOUDINARY_STORAGE = {
    'CLOUD_NAME': env('CLOUDINARY_CLOUD_NAME'),
    'API_KEY': env('CLOUDINARY_API_KEY'),
    'API_SECRET': env('CLOUDINARY_API_SECRET')
}


# Use Cloudinary for media files
DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'

# MEDIA_URL = '/media/' 


# whitenoise
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# Paystack Configuration
PAYSTACK_SECRET_KEY = env('PAYSTACK_SECRET_KEY', default='')
PAYSTACK_PUBLIC_KEY = env('PAYSTACK_PUBLIC_KEY', default='')

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = 'users.User'


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.AllowAny',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,  # Default page size for pagination
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "AUTH_HEADER_TYPES": ("Bearer",),
    }


SWAGGER_SETTINGS = {
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header',
            'description': 'JWT authorization using the Bearer scheme. Example: "Bearer {token}"'
        }
    },
    'USE_SESSION_AUTH': False,
    'JSON_EDITOR': True,
    'VALIDATOR_URL': None,  
    'OPERATIONS_SORTER': 'alpha',
    'TAGS_SORTER': 'alpha',
    'DEFAULT_MODEL_RENDERING': 'example', 
}

# Email Configuration
# Using cPanel email (mail.infitech-innovation.com)
# SSL/TLS Port 465 (recommended) or TLS Port 587

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = env('EMAIL_HOST', default='mail.infitech-innovation.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)  # Use 587 for TLS (more reliable in production)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='kifaru@infitech-innovation.com')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)  # TLS for port 587
EMAIL_USE_SSL = env.bool('EMAIL_USE_SSL', default=False)
EMAIL_TIMEOUT = 10  # Add timeout to prevent worker hangs
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='Kifaru Impact <kifaru@infitech-innovation.com>')

# Resend API (disabled until domain is verified)
RESEND_API_KEY = env('RESEND_API_KEY', default='')

JAZZMIN_SETTINGS = {
    "site_title": "Kifaru Impact Admin",
    "topmenu_links": [
        {"app": "booking"},
    ],
    "show_ui_builder": False,

}
JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": True,
    "brand_small_text": False,
    "brand_colour": False,
    "accent": "accent-primary",
    "navbar": "navbar-white navbar-light",
    "no_navbar_border": False,
    "navbar_fixed": False,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": False,
    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": False,
    "sidebar_nav_compact_style": True,
    "sidebar_nav_legacy_style": True,
    "sidebar_nav_flat_style": True,
    "theme": "yeti",
    "dark_mode_theme": None,
    "button_classes": {
        "primary": "btn-outline-primary",
        "secondary": "btn-outline-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success"
    }
}

FRONTEND_URL = env('FRONTEND_URL', default='http://localhost:5173')


# Currency settings
DEFAULT_CURRENCY = "EUR"

# Time zone settings for multiple locations
USE_TZ = True
TIME_ZONE = "Africa/Nairobi"  # Can be customized per property in the frontend

