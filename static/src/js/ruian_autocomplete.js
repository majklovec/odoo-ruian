odoo.define("partner_ruian.RUIANAutocomplete", function (require) {
  "use strict";

  const { debounce } = require("web.utils");
  const { Widget } = require("web.Widget");
  const { registry } = require("web.core");
  const session = require("web.session");

  const RUIANAutocomplete = Widget.extend({
    template: "RUIANAutocomplete",
    events: {
      "input .ruian-input": "handleInput",
      "focus .ruian-input": "handleFocus",
      "click .suggestion-item": "selectSuggestion",
    },

    init: function (parent, fieldInfo) {
      this._super(...arguments);
      this.streetId = null;
      this.suggestions = [];
      this.loading = false;
      this.fieldNames = ["street", "city", "zip", "ruian_code"];
    },

    start: function () {
      this.debouncedFetch = debounce(this.fetchSuggestions, 500);
      return this._super(...arguments);
    },

    handleInput: function (ev) {
      const query = ev.target.value.trim();
      if (query.length > 2) {
        this.debouncedFetch(query);
      }
    },

    handleFocus: function () {
      if (this.$input.val().length > 2) {
        this.fetchSuggestions(this.$input.val());
      }
    },

    async fetchSuggestions(query) {
      try {
        this.loading = true;
        this.toggleLoading(true);

        const suggestions = await this._rpc({
          model: "res.partner",
          method: "fetch_ruian_suggestions",
          args: [
            {
              query: query,
              streetId: this.streetId,
              stage: this.streetId ? "number_town" : "street",
            },
          ],
          context: session.user_context,
        });

        this.suggestions = suggestions;
        this.renderSuggestions();
      } finally {
        this.loading = false;
        this.toggleLoading(false);
      }
    },

    selectSuggestion: function (ev) {
      const $target = $(ev.currentTarget);
      const suggestion = $target.data("suggestion");

      if (suggestion.type === "street") {
        this.streetId = suggestion.payload.id;
        this.updateFields({
          street: suggestion.payload.name,
          city: "",
          zip: "",
          ruian_code: "",
        });
        this.$input.val(suggestion.payload.name + " ");
      } else {
        this.updateFields({
          street: this.$input.val().split(",")[0],
          city: suggestion.payload.city,
          zip: suggestion.payload.zip,
          ruian_code: suggestion.payload.id,
        });
        this.$input.val(
          `${this.$input.val().split(",")[0]}, ${suggestion.payload.city}, ${
            suggestion.payload.zip
          }`
        );
      }

      this.clearSuggestions();
    },

    updateFields: function (values) {
      this.fieldNames.forEach((field) => {
        if (values[field] !== undefined) {
          this.$(`[name="${field}"]`).val(values[field]).trigger("change");
        }
      });
    },

    renderSuggestions: function () {
      const $list = this.$(".suggestion-list").empty();

      this.suggestions.forEach((suggestion) => {
        $list.append(
          $(`<div class="suggestion-item" data-suggestion='${JSON.stringify(
            suggestion
          )}'>
                        ${this.highlightText(
                          suggestion.display,
                          this.$input.val()
                        )}
                       </div>`)
        );
      });

      this.$(".suggestion-list").toggle(this.suggestions.length > 0);
    },

    highlightText: function (text, query) {
      if (!query) return text;
      const regex = new RegExp(`(${this.escapeRegex(query)})`, "gi");
      return text.replace(regex, "<strong>$1</strong>");
    },

    escapeRegex: function (string) {
      return string.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    },

    clearSuggestions: function () {
      this.suggestions = [];
      this.$(".suggestion-list").empty().hide();
    },

    toggleLoading: function (show) {
      this.$(".ruian-spinner").toggle(show);
    },
  });

  registry.category("fields").add("ruian_autocomplete", RUIANAutocomplete);
  return RUIANAutocomplete;
});
