from django.urls import path
from .views import (
    UserRegisterView,
    LoginView,
    PasswordResetRequestView,
    SetNewPasswordView,
    UserDetailView,
    # Admin views
    UserListView,
    UserManageView,
    UserCreateView,
    UserStatsView,
)

app_name = 'users'

urlpatterns = [
    # Public endpoints
    path('register/', UserRegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path('password-reset-confirm/<str:uidb64>/<str:token>/', SetNewPasswordView.as_view(), name='password-reset-confirm'),
    path('me/', UserDetailView.as_view(), name='user-detail'),
    
    # Admin endpoints
    path('admin/users/', UserListView.as_view(), name='admin-user-list'),
    path('admin/users/create/', UserCreateView.as_view(), name='admin-user-create'),
    path('admin/users/<int:pk>/', UserManageView.as_view(), name='admin-user-manage'),
    path('admin/stats/', UserStatsView.as_view(), name='admin-user-stats'),
]
