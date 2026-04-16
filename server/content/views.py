from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import NewsletterSubscriber

@api_view(["POST"])
def newsletter_subscribe(request):
    email = request.data.get("email")
    if not email:
        return Response({"error": "Email required"}, status=status.HTTP_400_BAD_REQUEST)
    
    subscriber, created = NewsletterSubscriber.objects.get_or_create(
        email=email,
        defaults={"name": request.data.get("name", "")}
    )
    
    if created:
        return Response({"message": "Subscribed successfully"}, status=status.HTTP_201_CREATED)
    return Response({"message": "Already subscribed"}, status=status.HTTP_200_OK)

