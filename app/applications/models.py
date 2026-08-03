from django.db import models
from django.conf import settings
from opportunities.models import Opportunity
from cloudinary_storage.storage import RawMediaCloudinaryStorage

def resume_file_path(instance, filename):
    import os, uuid
    ext = os.path.splitext(filename)[1]
    filename = f'{uuid.uuid4()}{ext}'
    return f'afrivate/resumes/user_{instance.user.id}/{filename}'

# Create your models here.
class Application(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        # An accepted engagement that has run its course — set from the admin
        # dashboard (Admin Dashboard PRD 6.4) or future platform flow.
        ('completed', 'Completed'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='applications')
    opportunity = models.ForeignKey(Opportunity, on_delete=models.CASCADE, related_name='applicants')
    cover_letter = models.TextField(blank=True)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    
    resume = models.FileField(storage= RawMediaCloudinaryStorage(),upload_to=resume_file_path, null=True, blank=True)
    profile_resume = models.ForeignKey(
        "profiles.Credential",
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )

    
    applied_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        # jjust to ensures that a user can only apply once per opportunity
        unique_together = ('user', 'opportunity')
        ordering = ['-applied_at']

    def __str__(self):
        return f"{self.user.username} - {self.opportunity.title}"