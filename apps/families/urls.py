from django.urls import path

from . import auth_views, discovery_views, views

urlpatterns = [
    path("tree/start/", discovery_views.start_or_find_tree, name="start_or_find_tree"),
    path("tree/public/<slug:slug>/", discovery_views.public_tree_detail, name="public_tree_detail"),
    path("tree/public/<slug:slug>/request/", discovery_views.request_connection, name="family_request_connection"),
    path("tree/requests/", discovery_views.connection_requests_dashboard, name="family_connection_requests"),
    path(
        "tree/requests/<int:request_id>/<str:action>/",
        discovery_views.review_connection_request,
        name="family_connection_request_review",
    ),
    path("surnames/<slug:surname_slug>/", discovery_views.surname_detail, name="surname_detail"),
    path("tree/people/<int:person_id>/invite/", views.invite_person, name="family_invite_person"),
    path(
        "tree/people/<int:person_id>/invite-relative/<str:relation_type>/",
        views.invite_relative,
        name="family_invite_relative",
    ),
    path(
        "tree/people/<int:person_id>/bulk-add-relatives/",
        views.bulk_add_relatives,
        name="family_bulk_add_relatives",
    ),
    path("tree/people/<int:person_id>/set-anchor/", views.set_tree_anchor, name="family_set_tree_anchor"),
    path("invitations/<str:token>/", views.invitation_detail, name="family_invitation_detail"),
    path("invitations/<str:token>/accept/", views.invitation_accept, name="family_invitation_accept"),
    path("invitations/<str:token>/decline/", views.invitation_decline, name="family_invitation_decline"),
    path("invitations/<str:token>/ignore/", views.invitation_ignore, name="family_invitation_ignore"),
    path("families/switch/<slug:slug>/", views.switch_family, name="family_switch"),
    path("accounts/login/", auth_views.RateLimitedLoginView.as_view(), name="login"),
    path("accounts/signup/", auth_views.signup, name="signup"),
    path("accounts/password_reset/", auth_views.LocalDeveloperPasswordResetView.as_view(), name="password_reset"),
    path(
        "accounts/password_reset/done/",
        auth_views.LocalDeveloperPasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path("accounts/verify/sent/", auth_views.email_verification_sent, name="email_verification_sent"),
    path("accounts/verify/resend/", auth_views.resend_email_verification, name="email_verification_resend"),
    path("accounts/verify/<str:token>/", auth_views.verify_email, name="email_verify"),
]
