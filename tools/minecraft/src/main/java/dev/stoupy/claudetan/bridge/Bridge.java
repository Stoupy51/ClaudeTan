package dev.stoupy.claudetan.bridge;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.mojang.blaze3d.platform.InputConstants;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.function.Function;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientLifecycleEvents;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.message.v1.ClientReceiveMessageEvents;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.client.Screenshot;
import net.minecraft.client.gui.screens.ConnectScreen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.multiplayer.ServerData;
import net.minecraft.client.multiplayer.resolver.ServerAddress;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.item.ItemStack;

/** An HTTP server on localhost through which ClaudeTan drives this client: every route takes and returns JSON. */
public final class Bridge implements ClientModInitializer {
	/** The port, overridden by the system property claudetan.bridge.port. */
	static final int PORT = Integer.getInteger("claudetan.bridge.port", 47621);
	/** How long a route waits for the client thread, in seconds. */
	static final int TIMEOUT_S = 10;

	/** Every chat, system and action bar line received, in order; the chat route pages through it. */
	static final List<String> LINES = new ArrayList<>();
	/** Keys held down by the hold route, with the ticks left. Only the client thread touches it. */
	static final Map<KeyMapping, Integer> HELD = new HashMap<>();

	@Override
	public void onInitializeClient() {
		ClientReceiveMessageEvents.GAME.register((message, overlay) -> record((overlay ? "[actionbar] " : "") + message.getString()));
		ClientReceiveMessageEvents.CHAT.register((message, signed, sender, params, time) -> record(message.getString()));
		// Unfocused, the client must keep ticking, since the user works in other windows meanwhile.
		ClientLifecycleEvents.CLIENT_STARTED.register(client -> client.options.pauseOnLostFocus = false);
		ClientTickEvents.END_CLIENT_TICK.register(client -> tickHeldKeys());

		try {
			HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), PORT), 0);
			route(server, "/state", body -> state());
			route(server, "/chat", Bridge::chat);
			route(server, "/command", Bridge::command);
			route(server, "/hold", Bridge::hold);
			route(server, "/look", Bridge::look);
			route(server, "/connect", Bridge::connect);
			route(server, "/disconnect", body -> disconnect());
			route(server, "/quit", body -> quit());
			server.createContext("/screenshot", exchange -> answer(exchange, screenshot()));
			server.start();
			// Its dispatcher thread would keep the game from exiting.
			ClientLifecycleEvents.CLIENT_STOPPING.register(client -> server.stop(0));
		} catch (IOException e) {
			throw new IllegalStateException("The bridge cannot listen on port " + PORT, e);
		}
	}

	/** Runs a route on the client thread and answers with what it returns, or with {"error": ...}. */
	static void route(HttpServer server, String path, Function<JsonObject, JsonObject> handler) {
		server.createContext(path, exchange -> {
			JsonObject body = read(exchange.getRequestBody());
			CompletableFuture<JsonObject> result = Minecraft.getInstance().submit(() -> handler.apply(body));
			answer(exchange, result);
		});
	}

	static JsonObject read(InputStream stream) throws IOException {
		String text = new String(stream.readAllBytes(), StandardCharsets.UTF_8);
		return text.isBlank() ? new JsonObject() : JsonParser.parseString(text).getAsJsonObject();
	}

	static void answer(HttpExchange exchange, CompletableFuture<JsonObject> result) throws IOException {
		JsonObject response;
		try {
			response = result.get(TIMEOUT_S, TimeUnit.SECONDS);
		} catch (Exception e) {
			response = error(e.getCause() == null ? e.toString() : e.getCause().toString());
		}
		byte[] bytes = response.toString().getBytes(StandardCharsets.UTF_8);
		exchange.getResponseHeaders().set("Content-Type", "application/json");
		exchange.sendResponseHeaders(200, bytes.length);
		exchange.getResponseBody().write(bytes);
		exchange.close();
	}

	static JsonObject error(String message) {
		JsonObject object = new JsonObject();
		object.addProperty("error", message);
		return object;
	}

	static JsonObject ok() {
		JsonObject object = new JsonObject();
		object.addProperty("ok", true);
		return object;
	}

	static void record(String line) {
		synchronized (LINES) {
			LINES.add(line);
		}
	}

	/** Where the client is: its screen, and the player when in a world. */
	static JsonObject state() {
		Minecraft client = Minecraft.getInstance();
		JsonObject state = new JsonObject();
		state.addProperty("loading", client.gui.overlay() != null);
		state.addProperty("screen", client.gui.screen() == null ? null : client.gui.screen().getClass().getSimpleName());
		LocalPlayer player = client.player;
		if (player == null || client.level == null || client.gameMode == null) {
			return state;
		}

		JsonObject self = new JsonObject();
		self.addProperty("name", player.getName().getString());
		self.addProperty("dimension", client.level.dimension().identifier().toString());
		self.addProperty("gamemode", client.gameMode.getPlayerMode().getName());
		JsonArray position = new JsonArray();
		position.add(player.getX());
		position.add(player.getY());
		position.add(player.getZ());
		self.add("position", position);
		self.addProperty("yaw", player.getYRot());
		self.addProperty("pitch", player.getXRot());
		self.addProperty("health", player.getHealth());
		self.addProperty("food", player.getFoodData().getFoodLevel());
		self.addProperty("selected_slot", player.getInventory().getSelectedSlot());
		JsonArray hotbar = new JsonArray();
		for (int slot = 0; slot < 9; slot++) {
			hotbar.add(describe(player.getInventory().getItem(slot)));
		}
		self.add("hotbar", hotbar);
		state.add("player", self);
		return state;
	}

	static String describe(ItemStack stack) {
		if (stack.isEmpty()) {
			return "";
		}
		return stack.getCount() + " " + BuiltInRegistries.ITEM.getKey(stack.getItem()) + " \"" + stack.getHoverName().getString() + "\"";
	}

	/** The lines received from index "after" on, and the index to ask from next. */
	static JsonObject chat(JsonObject body) {
		int after = body.has("after") ? body.get("after").getAsInt() : 0;
		JsonObject page = new JsonObject();
		JsonArray lines = new JsonArray();
		synchronized (LINES) {
			LINES.subList(Math.min(after, LINES.size()), LINES.size()).forEach(lines::add);
			page.addProperty("next", LINES.size());
		}
		page.add("lines", lines);
		return page;
	}

	/** Sends a command as the player, without its slash; its feedback arrives in the chat. */
	static JsonObject command(JsonObject body) {
		if (Minecraft.getInstance().getConnection() == null) {
			return error("Not in a world.");
		}
		Minecraft.getInstance().getConnection().sendCommand(body.get("command").getAsString().replaceFirst("^/", ""));
		return ok();
	}

	/** Holds a key for some ticks, after one click so that taps such as attack or drop register. */
	static JsonObject hold(JsonObject body) {
		KeyMapping key = KeyMapping.get("key." + body.get("key").getAsString());
		if (key == null) {
			return error("Unknown key: forward, back, left, right, jump, sneak, sprint, use, attack, drop, swapOffhand, inventory or hotbar.1 to hotbar.9.");
		}
		KeyMapping.click(InputConstants.getKey(key.saveString()));
		key.setDown(true);
		HELD.put(key, body.has("ticks") ? body.get("ticks").getAsInt() : 1);
		return ok();
	}

	/** Pressing again every tick, since the client releases keys on its own when a screen opens or the window loses focus. */
	static void tickHeldKeys() {
		HELD.replaceAll((key, ticks) -> ticks - 1);
		HELD.forEach((key, ticks) -> key.setDown(ticks > 0));
		HELD.values().removeIf(ticks -> ticks <= 0);
	}

	static JsonObject look(JsonObject body) {
		LocalPlayer player = Minecraft.getInstance().player;
		if (player == null) {
			return error("Not in a world.");
		}
		player.setYRot(body.get("yaw").getAsFloat());
		player.setXRot(body.get("pitch").getAsFloat());
		return ok();
	}

	static JsonObject connect(JsonObject body) {
		Minecraft client = Minecraft.getInstance();
		String address = body.has("address") ? body.get("address").getAsString() : "localhost";
		ServerData server = new ServerData("ClaudeTan test", address, ServerData.Type.OTHER);
		ConnectScreen.startConnecting(new TitleScreen(), client, ServerAddress.parseString(address), server, false, null);
		return ok();
	}

	static JsonObject disconnect() {
		Minecraft client = Minecraft.getInstance();
		if (client.level == null) {
			return error("Not in a world.");
		}
		// As the pause menu's Disconnect button: the server sees the player leave at once.
		client.disconnectFromWorld(ClientLevel.DEFAULT_QUIT_MESSAGE);
		return ok();
	}

	static JsonObject quit() {
		// Stopping while resources load crashes the game natively.
		if (Minecraft.getInstance().gui.overlay() != null) {
			return error("Still loading, try again once state says loading: false.");
		}
		Minecraft.getInstance().stop();
		return ok();
	}

	/** Saves what the window shows into screenshots/, then answers with the file's absolute path. */
	static CompletableFuture<JsonObject> screenshot() {
		Minecraft client = Minecraft.getInstance();
		Path path = client.gameDirectory.toPath().resolve("screenshots").resolve(LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd_HH.mm.ss.SSS")) + ".png");
		CompletableFuture<JsonObject> saved = new CompletableFuture<>();
		client.execute(() -> Screenshot.takeScreenshot(client.gameRenderer.mainRenderTarget(), image -> {
			try (image) {
				Files.createDirectories(path.getParent());
				image.writeToFile(path);
				JsonObject result = new JsonObject();
				result.addProperty("path", path.toAbsolutePath().toString());
				saved.complete(result);
			} catch (IOException e) {
				saved.complete(error(e.toString()));
			}
		}));
		return saved;
	}
}
