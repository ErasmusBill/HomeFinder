from django.shortcuts import render

from django.core.paginator import Paginator
from .selectors import get_recent_properties, get_published_properties, get_property_by_slug, get_featured_properties
# Create your views here.

def home(request):
    # Show featured properties and recent verified & published properties on landing page
    featured = get_featured_properties(limit=8)
    recent = get_recent_properties(limit=8)
    return render(request, 'home_finder/index.html', {'featured_properties': featured, 'recent_properties': recent})

def get_all_properties(request):
    # properties = get_published_properties()
    #
    # paginator = Paginator(properties, 50)
    # page_number = request.GET.get('page')
    # page_obj = paginator.get_page(page_number)
    return render(request, 'home_finder/property_list.html')


def get_property_detail(request, slug):
    # property = get_property_by_slug(slug=slug)
    return render(request, 'home_finder/property_detail.html', {'slug': slug})
