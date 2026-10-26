import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('closet', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Interest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='swap_interests', to='closet.clothing')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='swap_interests', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at', '-id'],
                'constraints': [models.UniqueConstraint(fields=('user', 'item'), name='unique_swap_interest')],
            },
        ),
    ]
