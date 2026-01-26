from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from .serializers import (
    UserRegisterSerializer,
    LoginSerializer,
    LogoutSerializer,
    PasswordResetRequestSerializer,
    SetNewPasswordSerializer,
    UserListSerializer,
    UserStatsSerializer,
    UserProfileSerializer
)
from .models import User


class UserRegisterView(generics.GenericAPIView):
    serializer_class = UserRegisterSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({
            'message': 'User registered successfully.',
            'data': serializer.data
        }, status=status.HTTP_201_CREATED)


class LoginView(generics.GenericAPIView):
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class LogoutView(generics.GenericAPIView):
    serializer_class = LogoutSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({
            'message': 'Logout successful.'
        }, status=status.HTTP_200_OK)


class PasswordResetRequestView(generics.GenericAPIView):
    serializer_class = PasswordResetRequestSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({
            'message': 'Password reset link has been sent to your email.'
        }, status=status.HTTP_200_OK)


class SetNewPasswordView(generics.GenericAPIView):
    serializer_class = SetNewPasswordSerializer
    permission_classes = [AllowAny]

    def patch(self, request, uidb64, token):
        # Include uidb64 and token in the data
        data = request.data.copy()
        data['uidb64'] = uidb64
        data['token'] = token
        
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        return Response({
            'message': 'Password reset successful.'
        }, status=status.HTTP_200_OK)


class UserDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]
    
    def get_object(self):
        return self.request.user


# ========== ADMIN ENDPOINTS ==========

class UserListView(generics.ListAPIView):
    """Admin: List all users with search and filters"""
    queryset = User.objects.all()
    serializer_class = UserListSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['role', 'is_active', 'is_verified']
    search_fields = ['email', 'first_name', 'last_name']
    ordering_fields = ['date_joined', 'last_login']
    ordering = ['-date_joined']


class UserManageView(generics.RetrieveUpdateDestroyAPIView):
    """Admin: Get, update, or delete specific user"""
    queryset = User.objects.all()
    serializer_class = UserListSerializer
    permission_classes = [IsAdminUser]
    lookup_field = 'pk'


class UserCreateView(generics.CreateAPIView):
    """Admin: Create new user (bypasses normal registration)"""
    queryset = User.objects.all()
    serializer_class = UserRegisterSerializer
    permission_classes = [IsAdminUser]


class UserStatsView(generics.GenericAPIView):
    """
    Admin: Get user statistics.
    A simple serializer is provided so schema generation works.
    """
    permission_classes = [IsAdminUser]
    serializer_class = UserStatsSerializer

    def get(self, request, *args, **kwargs):
        # During schema generation drf-yasg sets `swagger_fake_view` on the view —
        # return a minimal response so schema generation can proceed.
        if getattr(self, "swagger_fake_view", False):
            return Response({}, status=status.HTTP_200_OK)

        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        verified_users = User.objects.filter(is_verified=True).count()

        users_by_role = {
            role[0]: User.objects.filter(role=role[0]).count()
            for role in User.ROLE_CHOICES
        }

        data = {
            "total_users": total_users,
            "active_users": active_users,
            "verified_users": verified_users,
            "users_by_role": users_by_role,
        }
        return Response(self.get_serializer(data).data, status=status.HTTP_200_OK)
