import { withKnobs, boolean } from "@storybook/addon-knobs"
import React from "react"
import ThreadPostsModeration from "./ThreadPostsModeration"

export default {
  title: "Route/Thread/Moderation",
  decorators: [withKnobs],
}

export const PostsOptions = () => (
  <ThreadPostsModeration
    moderation={{
      loading: boolean("Loading", false),
      actions: [
        {
          name: "Delete posts",
          icon: "times",
          iconSolid: true,
          action: () => {},
        },
      ],
    }}
    selection={{ selected: [1], clear: () => {} }}
  />
)
