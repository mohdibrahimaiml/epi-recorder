import { corsPreflight, proxyToRender } from "../_proxy.js";

export async function onRequest(context) {
  if (context.request.method === "OPTIONS") {
    return corsPreflight(context);
  }
  return proxyToRender(context);
}
