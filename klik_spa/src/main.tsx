import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import router from "./router";
import "./index.css";
import FrappeProviderWrapper from "./providers/FrappeProviderWrapper";
import { installPosShortcutListener } from "./utils/posShortcuts";
import { withCsrfRetry } from "./utils/csrfRetry";

// Before anything renders, so Firefox never gets a bare F10 on any page.
installPosShortcutListener();
window.fetch = withCsrfRetry(window.fetch.bind(window), window as { csrf_token?: string });

// ReactDOM.createRoot(document.getElementById("root")!).render(
//   <React.StrictMode>
//     <RouterProvider router={router} />
//   </React.StrictMode>
// );

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <FrappeProviderWrapper>
      <RouterProvider router={router} />
    </FrappeProviderWrapper>
  </React.StrictMode>
);
