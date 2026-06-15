from django.urls import path

from . import views

urlpatterns = [
    path("tree/people/<int:person_id>/invite/", views.invite_person, name="family_invite_person"),
    path(
        "tree/people/<int:person_id>/invite-relative/<str:relation_type>/",
        views.invite_relative,
        name="family_invite_relative",
    ),
    path("tree/people/<int:person_id>/set-anchor/", views.set_tree_anchor, name="family_set_tree_anchor"),
    path("invitations/<str:token>/", views.invitation_detail, name="family_invitation_detail"),
    path("invitations/<str:token>/accept/", views.invitation_accept, name="family_invitation_accept"),
    path("invitations/<str:token>/decline/", views.invitation_decline, name="family_invitation_decline"),
    path("invitations/<str:token>/ignore/", views.invitation_ignore, name="family_invitation_ignore"),
    path("families/switch/<slug:slug>/", views.switch_family, name="family_switch"),
    path("accounts/signup/", views.signup, name="signup"),
]
