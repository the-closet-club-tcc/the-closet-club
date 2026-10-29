from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('swap', '0008_reconcile_swap_workflow'),
        ('accounts', '0003_alter_review_rating'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SwapReview',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('review', models.OneToOneField(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='swap_review', to='accounts.review')),
                ('reviewer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='swap_reviews', to=settings.AUTH_USER_MODEL)),
                ('swap_request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to='swap.swaprequest')),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('swap_request', 'reviewer'), name='unique_review_per_swap_user')],
            },
        ),
    ]
