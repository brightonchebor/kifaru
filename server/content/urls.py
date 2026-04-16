# Content app has only NewsletterSubscriber model now
from django.urls import path
from .views import newsletter_subscribe

app_name = "content"

urlpatterns = [
    path("newsletter/subscribe/", newsletter_subscribe, name="newsletter-subscribe"),
]
