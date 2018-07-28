from django.db import models
from django.urls import reverse
from datetime import datetime, timedelta
import pytz
import os
import sendgrid
from sendgrid.helpers.mail import *
import uuid
from django.template.loader import render_to_string
from django.contrib.auth.models import (
    BaseUserManager, AbstractBaseUser, PermissionsMixin
)
from django.conf import settings

utc = pytz.UTC

LOG_TYPES = (
    ('generic', 'Generic log entry'),
    ('usage', 'Generic usage access'),
    ('stripe', 'Stripe related event'),
    ('spacebucks', 'Spacebucks related event'),
    ('profile', 'Member profile edited'),
    ('interlock', 'Interlock related event'),
    ('door', 'Door related event'),
    ('email', 'Email send event'),
    ('admin', 'Generic admin event'),
    ('error', 'Some event that causes an error'),
)

class Log(models.Model):
    logtype = models.CharField(
        "Type of action/event", choices=LOG_TYPES, max_length=30)
    description = models.CharField(
        "Description of action/event", max_length=500)
    data = models.TextField("Extra data for debugging action/event")
    date = models.DateTimeField(auto_now_add=True)


class UserEventLog(Log):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, "User affected by action")


class EventLog(Log):
    pass


# this needs to be here because it relies on the models defined above
from memberportal.helpers import log_user_event


class UserManager(BaseUserManager):
    def create_user(self, email, password=None):
        """
        Creates and saves a User with the given email and password.
        """
        if not email:
            raise ValueError('Users must have an email address')

        user = self.model(
            email=self.normalize_email(email),
        )

        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_staffuser(self, email, password):
        """
        Creates and saves a staff user with the given email and password.
        """
        user = self.create_user(
            email,
            password=password,
        )
        user.staff = True
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password):
        """
        Creates and saves a superuser with the given email and password.
        """
        user = self.create_user(
            email,
            password=password,
        )
        user.staff = True
        user.admin = True
        user.save(using=self._db)
        return user


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(
        verbose_name='email address',
        max_length=255,
        unique=True,
    )
    password_reset_key = models.UUIDField(default=None, blank=True, null=True)
    password_reset_expire = models.DateTimeField(
        default=None, blank=True, null=True)
    staff = models.BooleanField(default=False)  # a admin user; non super-user
    admin = models.BooleanField(default=False)  # a superuser
    # notice the absence of a "Password field", that's built in.

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []  # Email & Password are required by default.

    objects = UserManager()

    def __str__(self):
        return self.email

    @property
    def is_staff(self):
        "Is the user a member of staff?"
        return self.staff

    @property
    def is_admin(self):
        "Is the user a admin member?"
        return self.admin

    def clean_username(self):
        # Since User.username is unique, this check is redundant,
        # but it sets a nicer error message than the ORM. See #13147.
        username = self.cleaned_data["username"]
        if self.instance.username == username:
            return username
        try:
            User._default_manager.get(username=username)
        except User.DoesNotExist:
            return username
        raise forms.ValidationError(
            "Sorry, that email has already been used.",
            code='duplicate_username',
        )

    def __send_email(self, subject, body):
        if "SENDGRID_API_KEY" in os.environ:
            sg = sendgrid.SendGridAPIClient(
                apikey=os.environ.get('SENDGRID_API_KEY'))
            from_email = sendgrid.Email(settings.FROM_EMAIL)
            to_email = sendgrid.Email(self.email)
            subject = subject
            content = Content("text/html", body)
            mail = Mail(from_email, subject, to_email, content)
            response = sg.client.mail.send.post(request_body=mail.get())

            if response.status_code == 202:
                log_user_event(
                    self, "Sent email with subject: " + subject, "email",
                               "Email content: " + body)
                return True

        log_user_event(
            self, "Failed to send email with subject: " + subject,
            "email", "Email content: " + body)
        return False

    def email_notification(self, subject, title, preheader, message):
        email_vars = {"preheader": preheader,
                      "title": title, "message": message}
        email_string = render_to_string(
            'email_without_button.html', {'email': email_vars})

        if self.__send_email(subject, email_string):
            return True

    def email_link(self, subject, title, preheader, message, link, btn_text):
        email_vars = {"preheader": preheader,
                      "title": title,
                      "message": message,
                      "link": link,
                      "btn_text": btn_text}
        email_string = render_to_string(
            'email_with_button.html', {'email': email_vars})

        if self.__send_email(subject, email_string):
            return True

        return False

    def email_welcome(self):
        email_string = render_to_string('email_welcome.html')

        if self.__send_email("Welcome to HSBNE", email_string):
            return True

        return False

    def email_disable_member(self):
        if self.email_notification(
                "Your HSBNE site access has been disabled.",
                "Your access has been disabled.",
                "Your HSBNE site access has been disabled.",
                "Your access to HSBNE has been disabled. This could be due to overdue membership fees, a ban being "
                "issued or your membership ending. If this is temporary, you are not allowed back on site until your "
                "membership has been reactivated."):
            return True

        return False

    def email_enable_member(self):
        if self.email_notification(
                "Your HSBNE site access has been enabled.",
                "Your access has been enabled.",
                "Your HSBNE site access has been enabled.",
                "Great news! Your access to HSBNE has been enabled."):
            return True

        return False

    def reset_password(self):
        log_user_event(self, "Password reset requested", "profile")
        self.password_reset_key = uuid.uuid4()
        self.password_reset_expire = datetime.now() + timedelta(hours=24)
        self.save()
        self.email_link(
            "Password reset request for you HSBNE account",
            "HSBNE Password Reset",
            "Password reset request for you HSBNE account",
            "Someone has issued a password reset for your HSBNE account. "
            "The link below will expire in 24 hours. If this wasn't you, "
            "just ignore this email and nothing will happen.",
            "https://portal.hsbne.org" + reverse(
                'reset_password',
                kwargs={'reset_token': self.password_reset_key}),
            "Reset Password")

        return True


class MemberTypes(models.Model):
    name = models.CharField("Member Type Name", max_length=20)
    conditions = models.CharField("Membership Conditions", max_length=100)
    cost = models.IntegerField("Monthly Cost")

    def __str__(self):
        return self.name + " - ${} per mth. {}".format(
            self.cost, self.conditions)


class Profile(models.Model):
    STATES = (
        ('noob', 'New Member'),
        ('active', 'Active Member'),
        ('inactive', 'Inactive Member'),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    screen_name = models.CharField("Screen Name", max_length=30)
    first_name = models.CharField("First Name", max_length=30)
    last_name = models.CharField("Last Name", max_length=30)
    state = models.CharField(max_length=8, default='noob', choices=STATES)
    member_type = models.ForeignKey(
        MemberTypes, on_delete=models.PROTECT, related_name='member_type')
    causes = models.ManyToManyField('causes.Causes')
    rfid = models.CharField(
        "RFID Tag", max_length=20, unique=True, null=True, blank=True)
    doors = models.ManyToManyField('access.Doors', blank=True)
    spacebucks_balance = models.FloatField(default=0.0)
    stripe_customer_id = models.CharField(
        max_length=100, blank=True, null=True, default="")
    stripe_card_expiry = models.CharField(
        max_length=10, blank=True, null=True, default="")
    stripe_card_last_digits = models.CharField(
        max_length=4, blank=True, null=True, default="")

    def deactivate(self):
        log_user_event(self.user, "Deactivated member", "profile")
        self.user.email_disable_member()
        self.state = "inactive"
        self.save()

    def activate(self):
        log_user_event(self.user, "Activated member", "profile")
        if self.state == "noob":
            self.user.email_welcome()

        else:
            self.user.email_enable_member()

        self.state = "active"
        self.save()

    def get_logs(self):
        return UserEventLog.objects.filter(user=self.user)

    def __str__(self):
        return str(self.user)

    def get_full_name(self):
        # The user is identified by their email address
        return self.first_name + " " + self.last_name

    def get_short_name(self):
        # The user is identified by their email address
        return self.first_name