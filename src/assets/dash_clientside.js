window.dash_clientside = Object.assign({}, window.dash_clientside, {
  leaflet: {
    pointToLayer: function (feature, latlng, context) {
      return L.circleMarker(latlng, {
        radius: 5,
        fillColor: feature.properties.marker_color,
        color: "white",
        weight: 1,
        opacity: 1,
        fillOpacity: 0.8,
      }).bindTooltip(feature.properties.tooltip);
    },
    clusterToLayer: function (feature, latlng, index, context) {
      console.log(feature);
      console.log(index);
      console.log(context);

      const count = feature.properties.point_count;
      const size = count < 100 ? 30 : count < 1000 ? 40 : 50;
      const color = "#555"; // Default cluster color
      const icon = L.divIcon({
        html: `<div style="background-color: ${context.fillColor}; width: ${size}px; height: ${size}px; border-radius: 50%; display: flex; align-items:center; justify-content:center; color: white; border: 2px solid white; font-weight: bold;">${count}</div>`,
        className: "marker-cluster",
        iconSize: L.point(size, size),
      });
      return L.marker(latlng, { icon: icon });
    },
  },
  clientside: {
    clean_filters: function (trigger) {
      if (!trigger) {
        return window.dash_clientside.no_update;
      }

      // Helper to set value on a React text input
      const setNativeValue = (element, value) => {
        const valueSetter = Object.getOwnPropertyDescriptor(
          element,
          "value"
        ).set;
        const prototype = Object.getPrototypeOf(element);
        const prototypeValueSetter = Object.getOwnPropertyDescriptor(
          prototype,
          "value"
        ).set;

        if (valueSetter && valueSetter !== prototypeValueSetter) {
          prototypeValueSetter.call(element, value);
        } else {
          valueSetter.call(element, value);
        }

        element.dispatchEvent(new Event("input", { bubbles: true }));
      };

      const cleanInputs = () => {
        const inputs = document.querySelectorAll(
          '.dash-filter input[type="text"]'
        );
        inputs.forEach((input) => {
          let val = input.value;
          let original = val;

          // Remove "icontains " prefix
          if (/^icontains\s+/i.test(val)) {
            val = val.replace(/^icontains\s+/i, "");
            // Check for surrounding quotes (single or double) and remove them
            if (
              (val.startsWith('"') && val.endsWith('"')) ||
              (val.startsWith("'") && val.endsWith("'"))
            ) {
              val = val.substring(1, val.length - 1);
            }
          }
          // Handle relational operators (i<, s>, i<=, etc.)
          else if (/^[is][<>]=?/i.test(val)) {
            val = val.substring(1);
          }

          if (val !== original) {
            try {
              // Try setting it the React-friendly way
              setNativeValue(input, val);
            } catch (e) {
              // Fallback to direct assignment if fancy way fails
              input.value = val;
            }
          }
        });
      };

      // Use MutationObserver to wait for table to appear/update
      const observer = new MutationObserver((mutations) => {
        cleanInputs();
      });

      const target = document.querySelector(".dash-table-container");
      if (target) {
        observer.observe(target, {
          childList: true,
          subtree: true,
          attributes: true,
          attributeFilter: ["value"],
        });

        // Disconnect after 5 seconds
        setTimeout(() => {
          observer.disconnect();
        }, 5000);

        // Also try immediately just in case
        cleanInputs();
      } else {
        // Poll briefly if container not found yet
        const checkInterval = setInterval(() => {
          const t = document.querySelector(".dash-table-container");
          if (t) {
            clearInterval(checkInterval);
            observer.observe(t, { childList: true, subtree: true });
            setTimeout(() => observer.disconnect(), 5000);
            cleanInputs();
          }
        }, 200);

        // Stop polling after 2s if still nothing
        setTimeout(() => clearInterval(checkInterval), 2000);
      }

      return window.dash_clientside.no_update;
    },
  },
});
