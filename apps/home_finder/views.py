from django.shortcuts import render

from django.core.paginator import Paginator
from .selectors import get_recent_properties, get_published_properties, get_property_by_slug
# Create your views here.

def home(request):
    properties = get_recent_properties()
    return render(request, 'home_finder/index.html', {'properties': properties})

def get_all_properties(request):
    properties = get_published_properties()
    
    paginator = Paginator(properties, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'home_finder/property_list.html', {'properties': page_obj})


def get_property_detail(request, slug):
    property_obj = get_property_by_slug(slug=slug)
    
    if property_obj:
        from django.db.models import F
        from apps.home_finder.models import Property
        
        viewed_cookie_name = f'viewed_property_{property_obj.id}'
        if not request.COOKIES.get(viewed_cookie_name):
            # Only increment if the cookie is not present
            Property.objects.filter(id=property_obj.id).update(views_count=F("views_count") + 1)
            # The view count won't be updated on the property_obj itself unless we refresh,
            # but that's fine since it will be accurate on the next load.
            
    response = render(request, 'home_finder/property_detail.html', {'property': property_obj})
    
    if property_obj and not request.COOKIES.get(viewed_cookie_name):
        response.set_cookie(viewed_cookie_name, 'true', max_age=86400) # 24 hours
        
    return response