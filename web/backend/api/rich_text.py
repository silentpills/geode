"""Rich-text fields used for station metadata and visit comments."""

import nh3
from rest_framework import serializers


# Quill's toolbar formats and the list classes used in GeoDE's web and PDF views.
_COMMENT_CLEANER = nh3.Cleaner(
    tags={
        "p", "br", "strong", "b", "em", "i", "s", "strike", "u", "code",
        "pre", "ol", "ul", "li", "blockquote", "span", "a",
    },
    attributes={"a": {"href"}},
    tag_attribute_values={"a": {"target": {"_blank"}}},
    url_schemes={"https", "http", "mailto"},
    url_relative="deny",
    allowed_classes={
        "span": {"ql-size-small", "ql-size-normal", "ql-size-large", "ql-size-huge"},
        "pre": {"ql-syntax"},
        "ol": {"list-decimal", "ps-[19.5px]", "pl-[19.5px]"},
        "ul": {"list-disc", "ps-[19.5px]", "pl-[19.5px]"},
    },
)


class RichTextField(serializers.CharField):
    def to_internal_value(self, data):
        return _COMMENT_CLEANER.clean(super().to_internal_value(data))

    def to_representation(self, value):
        # Historical imports can contain markup written before field validation.
        return _COMMENT_CLEANER.clean(super().to_representation(value))
