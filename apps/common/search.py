import logging
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import QuerySet, F

logger = logging.getLogger(__name__)

def update_search_vector(instance, vector):
    """
    Updates the search_vector field on the given instance using a database-level update.
    """
    if not instance.pk:
        logger.warning(f"Attempted to update search vector for unsaved instance: {instance}")
        return

    model_class = instance.__class__
    try:
        model_class.objects.filter(pk=instance.pk).update(search_vector=vector)
    except Exception as e:
        logger.error(f"Failed to update search vector for {model_class.__name__} {instance.pk}: {e}")

def apply_search_filter(queryset: QuerySet, search_term: str, vector_field: str = 'search_vector') -> QuerySet:
    """
    Applies Full-Text Search filtering and ranking using websearch and prefix matching.
    """
    if not search_term:
        return queryset

    term = search_term.strip()

    if ' ' not in term:
        sanitized = term.replace("'", "").replace("\\", "").replace(":", "")
        if sanitized:
            query = SearchQuery(f"{sanitized}:*", search_type='raw')
        else:
            query = SearchQuery(term)
    else:
        query = SearchQuery(term, search_type='websearch')

    filter_kwargs = {vector_field: query}
    qs = queryset.filter(**filter_kwargs)
    qs = qs.annotate(rank=SearchRank(F(vector_field), query)).order_by('-rank')

    return qs