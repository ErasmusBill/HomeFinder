@@
 class Property(BaseModel):
@@
     is_furnished = models.BooleanField(default=False)
     is_available = models.BooleanField(default=True)
+    is_featured = models.BooleanField(default=False, help_text="Whether this property is featured on the homepage")
@@
