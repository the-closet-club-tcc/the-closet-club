from django.db import migrations, models
import django.db.models.deletion


def link_existing_reviews(apps, schema_editor):
    links = apps.get_model('swap', 'SwapReview').objects.using(schema_editor.connection.alias)
    reviews = apps.get_model('accounts', 'Review').objects.using(schema_editor.connection.alias)
    for link in links.exclude(review_id=None).select_related('review', 'swap_request').iterator():
        review, proposal = link.review, link.swap_request
        participants = {proposal.sender_id, proposal.recipient_id}
        if (
            proposal.status != 'completed'
            or review.pemberi_review_id != link.reviewer_id
            or review.pemberi_review_id == review.penerima_review_id
            or {review.pemberi_review_id, review.penerima_review_id} != participants
            or review.swap_request_id not in (None, proposal.pk)
            or reviews.filter(swap_request_id=proposal.pk, pemberi_review_id=link.reviewer_id).exclude(pk=review.pk).exists()
        ):
            raise RuntimeError(f'Review link {link.pk} needs reconciliation before migration; no reviews have been deleted.')
        reviews.filter(pk=review.pk, swap_request_id=None).update(swap_request_id=proposal.pk)


class Migration(migrations.Migration):
    dependencies = [
        ('swap', '0009_swapreview'),
        ('accounts', '0004_review_swap_request'),
    ]

    operations = [
        migrations.AlterField(
            model_name='swapreview',
            name='swap_request',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='review_links', to='swap.swaprequest'),
        ),
        migrations.RunPython(link_existing_reviews, migrations.RunPython.noop),
    ]
