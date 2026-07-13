from django.db import models
from django.utils import timezone
from datetime import timedelta
from django.conf import settings

# Create your models here.
class Opportunity(models.Model):
    class Category(models.TextChoices):
        VOLUNTEERING = 'volunteering', 'Volunteering'
        INTERNSHIP = 'internship', 'Internship'
        SCHOLARSHIP = 'scholarship', 'Scholarship'
        MENTORSHIP = 'mentorship', 'Mentorship'
        FELLOWSHIP = 'fellowship', 'Fellowship'
        CONTRACT = 'contract', 'Contract'
        FULL_TIME = 'full_time', 'Full-time'
        PART_TIME = 'part_time', 'Part-time'

    title = models.CharField(max_length=255, null=False, blank=False)
    opportunity_type = models.CharField(max_length=100, choices=Category.choices, default=Category.VOLUNTEERING, db_index=True)
    description = models.TextField()
    link = models.URLField(null=False, blank=False)
    # location = models.CharField(max_length=255, null=True, blank=True)  # e.g Remote, On-site
    posted_at = models.DateTimeField(auto_now_add=True)
    is_open = models.BooleanField(default=True,db_index=True)
    # Optional applicant target set by the enabler; null means no target.
    target_applicants = models.PositiveIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_opportunities')  # very important for permissions and filtering

    class Meta:
        ordering = ['-posted_at']
        unique_together = ('title', 'link')  # Prevent duplicate opportunities

    def __str__(self):
        return self.title
    
    def can_edit(self):
        # Allow editing only within 12 hours of posting
        return timezone.now() < self.posted_at + timedelta(hours=12)
    
    def save(self, *args, **kwargs):
        # Auto-close opportunity if it's too old (optional logic)
        super().save(*args, **kwargs)