import logging
from django.core.cache import cache

logger = logging.getLogger(__name__)

def invalidate_property_cache(property_obj=None, landlord_id=None, property_id=None):
    try:
        # Use django-redis delete_pattern to efficiently clear all property keys
        if hasattr(cache, "delete_pattern"):
            cache.delete_pattern("properties:*")
            cache.delete_pattern("home_finder:properties:*")
        else:
            # Fallback (may leave wildcards like search/price stale)
            cache.delete("properties:published")
            cache.delete("properties:featured:8")
            cache.delete("properties:recent:12")
            cache.delete("home_finder:properties:all")
            
            p_id = property_obj.pk if property_obj else property_id
            l_id = property_obj.landlord_id if property_obj else landlord_id

            if property_obj:
                cache.delete(f"properties:slug:{property_obj.slug}")
                if property_obj.region_id:
                    cache.delete(f"properties:region:{property_obj.region_id}")
                if property_obj.district_id:
                    cache.delete(f"properties:district:{property_obj.district_id}")
                if property_obj.area_id:
                    cache.delete(f"properties:area:{property_obj.area_id}")

            if p_id:
                cache.delete(f"properties:detail:{p_id}")
                cache.delete(f"home_finder:properties:detail:{p_id}")
            if l_id:
                cache.delete(f"home_finder:properties:user_{l_id}")
    except Exception as e:
        logger.error(f"Error invalidating property cache: {e}")

def invalidate_amenities_cache():
    cache.delete("home_finder:amenities:all")

def invalidate_documents_cache(landlord_id=None, document_id=None):
    if landlord_id:
        cache.delete(f"home_finder:documents:landlord_{landlord_id}")
    if document_id:
        cache.delete(f"home_finder:documents:detail:{document_id}")
    cache.delete("home_finder:documents:all")

def invalidate_locations_cache():
    cache.delete("properties:locations")

def invalidate_subscription_plans_cache():
    # Cache invalidation must never prevent a subscription plan from being
    # created or updated when Redis is temporarily unavailable. The plan
    # remains correct in the database; at worst a cached plan list lives
    # until its normal expiry.
    try:
        cache.delete("active_subscription_plans_cache")
    except Exception as exc:
        logger.warning("Unable to invalidate the subscription plans cache: %s", exc)
