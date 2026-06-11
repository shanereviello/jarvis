import asyncio

from app.agent import ask_jarvis


async def main():
    print("Jarvis ready. Type 'exit' to quit.\n")

    while True:
        user_input = input("You: ")

        if user_input.lower() in {"exit", "quit"}:
            break

        answer = await ask_jarvis(user_input)
        print(f"\nJarvis:\n{answer}\n")


if __name__ == "__main__":
    asyncio.run(main())

