"""Bootstrap an admin dashboard account (the AdminUser equivalent of createsuperuser):

    python manage.py create_admin --email ops@afrivate.org --name "Full Name"

Prompts for a password if --password is not given.
"""

import getpass

from django.core.management.base import BaseCommand, CommandError

from adminpanel.models import AdminUser


class Command(BaseCommand):
    help = 'Create an AdminUser for the admin dashboard.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True)
        parser.add_argument('--name', required=True, help='Full name')
        parser.add_argument('--password', help='If omitted, you will be prompted.')

    def handle(self, *args, **options):
        email = options['email'].lower().strip()
        if AdminUser.objects.filter(email=email).exists():
            raise CommandError(f'An admin with email {email} already exists.')

        password = options.get('password')
        if not password:
            password = getpass.getpass('Password: ')
            confirm = getpass.getpass('Password (again): ')
            if password != confirm:
                raise CommandError('Passwords did not match.')
        if len(password) < 8:
            raise CommandError('Password must be at least 8 characters.')

        admin = AdminUser(full_name=options['name'].strip(), email=email)
        admin.set_password(password)
        admin.save()
        self.stdout.write(self.style.SUCCESS(f'Admin user created: {admin.email}'))
