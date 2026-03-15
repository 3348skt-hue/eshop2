from django import template

register = template.Library()

@register.filter
def image_src(image_field):
    """Return correct image URL whether stored as external URL or local file"""
    if not image_field:
        return ''
    value = str(image_field)
    if value.startswith('http://') or value.startswith('https://'):
        return value
    # Local file - return media URL
    return '/media/' + value
