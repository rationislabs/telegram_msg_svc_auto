import sys

from . import answer, bot

if sys.argv[1:2] == ["answer"]:
    sys.exit(answer.main())
sys.exit(bot.main(sys.argv[1:]))
