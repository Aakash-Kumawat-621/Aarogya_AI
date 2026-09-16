import { QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";

export const getRouter = () => {
  const queryClient = new QueryClient();

  const router = createRouter({
    routeTree,
    context: { queryClient },
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
    defaultErrorComponent: ({ error, reset }) => <div className="p-8">Something went wrong. <button onClick={reset}>Try again</button></div>,
    defaultNotFoundComponent: () => <div className="p-8">Page not found.</div>,
  });

  return router;
};
