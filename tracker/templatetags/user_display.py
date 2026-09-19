from django import template


register = template.Library()


@register.filter
def display_name(user) -> str:
    if not user:
        return ""
    full_name = (user.get_full_name() or "").strip()
    if full_name:
        return full_name
    first_name = (getattr(user, "first_name", "") or "").strip()
    if first_name:
        return first_name
    return "Без имени"

