from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Django templates have no `dict[variable]` syntax -- used to look up
    a category's move list out of category_moves by the category's slug."""
    return mapping.get(key)


@register.filter
def zip_lists(a, b):
    """Pairs two equal-length lists up for `{% for x, y in a|zip_lists:b %}`
    -- used to walk the type-matrix's column headers alongside a row's
    values, since Django templates have no built-in zip."""
    return zip(a, b)
